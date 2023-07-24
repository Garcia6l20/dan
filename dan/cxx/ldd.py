from pathlib import Path
from dan.cxx import Executable, Library
from dan.core import asyncio
from dan import logging

import typing as t

import os
import functools
import glob
from elftools.elf import elffile


log = logging.getLogger(__name__)

def find_file_ignore_case(dirname, filename):
    if not os.path.exists(dirname):
        return None
    (root, _, filenames) = next(os.walk(dirname))
    filename_lower = filename.lower()
    for f in filenames:
        if f.lower() == filename_lower:
            return os.path.join(root, f)
    return None


if os.name == 'nt':
    import pefile

    def get_pe_deps(pe_data):
        deps = []
        if hasattr(pe_data, 'DIRECTORY_ENTRY_IMPORT'):
            for imp in pe_data.DIRECTORY_ENTRY_IMPORT:
                deps.append(imp.dll.decode())
        return deps


    def find_dll(dll, dll_lookup_dirs, arch):
        for dir in dll_lookup_dirs:
            dll_path = find_file_ignore_case(dir, dll)
            if not dll_path:
                continue
            pe_data = pefile.PE(dll_path)
            if pe_data.FILE_HEADER.Machine == arch:
                return (dll, dll_path, get_pe_deps(pe_data))
        return (dll, None, None)

    async def pe_tree(pe, lookup_dirs):
        libs = {} # stores all dlls we encounter, specifically {(basename(dll)).lower(): abspath(dll)}
        deps = {} # stores pe -> [dll] relations, specifically {abspath(pe): [basename(pe's direct dll dep)]}

        data = pefile.PE(pe)
        arch = data.FILE_HEADER.Machine

        async def _dep_tree(bin, bin_deps):
            bin = os.path.abspath(bin)
            if bin in deps:
                # aleady processed before
                return
            deps[bin] = bin_deps
            results = []
            # pefile.PE() takes very long time to run, so use multiprocessing to speed it up        
            async with asyncio.TaskGroup() as group:
                for dll in bin_deps:
                    if dll.lower() not in libs:
                        group.create_task(asyncio.async_wait(find_dll, dll, lookup_dirs, arch))

            results = group.results()
            for dll, dll_path, _deps in results:
                # store the found dll
                if dll_path:
                    libs[dll.lower()] = dll_path
                # note that the dll wasn't found, so that we don't try to look for it again
                else:
                    libs[dll.lower()] = None
            # recursively process newly found dlls
            async with asyncio.TaskGroup() as group:
                for dll, dll_path, dll_deps in results:
                    if dll_path:
                        await _dep_tree(dll_path, dll_deps)

        await _dep_tree(pe, get_pe_deps(data))
        return (libs, deps)
    
    async def dep_list(path, lookup_dirs):
        result = list()
        dlls, _deps = await pe_tree(path, lookup_dirs)
        for dll, dll_path in sorted(dlls.items(), key=lambda e: e[0].casefold()):
            result.append((dll, dll_path))
        return result
else:
    import errno
        
    def normpath(path: str) -> str:
        return os.path.normpath(path).replace('//', '/')


    def readlink(path: str, root: str, prefixed: bool = False) -> str:
        root = root.rstrip('/')
        if prefixed:
            path = path[len(root):]

        while os.path.islink(root + path):
            path = os.path.join(os.path.dirname(path), os.readlink(root + path))

        return normpath((root + path) if prefixed else path)


    def dedupe(items: t.List[str]) -> t.List[str]:
        seen = {}  # type: Dict[str, str]
        return [seen.setdefault(x, x) for x in items if x not in seen]


    def parse_ld_paths(str_ldpaths, root='', path=None) -> t.List[str]:
        ldpaths = []  # type: List[str]
        for ldpath in str_ldpaths.split(':'):
            if ldpath == '':
                # The ldso treats "" paths as $PWD.
                ldpath = os.getcwd()
            elif '$ORIGIN' in ldpath:
                ldpath = ldpath.replace('$ORIGIN',
                                        os.path.dirname(os.path.abspath(path)))
            else:
                ldpath = root + ldpath
            ldpaths.append(normpath(ldpath))
        return [p for p in dedupe(ldpaths) if os.path.isdir(p)]


    @functools.lru_cache()
    def parse_ld_so_conf(ldso_conf: str,
                        root: str = '/',
                        _first: bool = True) -> t.List[str]:
        paths = []  # type: List[str]

        dbg_pfx = '' if _first else '  '
        try:
            with open(ldso_conf) as f:
                for line in f.readlines():
                    line = line.split('#', 1)[0].strip()
                    if not line:
                        continue
                    if line.startswith('include '):
                        line = line[8:]
                        if line[0] == '/':
                            line = root + line.lstrip('/')
                        else:
                            line = os.path.dirname(ldso_conf) + '/' + line
                        log.debug('%s  glob: %s', dbg_pfx, line)
                        for path in glob.glob(line):
                            paths += parse_ld_so_conf(path,
                                                    root=root,
                                                    _first=False)
                    else:
                        paths += [normpath(root + line)]
        except IOError as e:
            if e.errno != errno.ENOENT:
                log.warning(e)

        if _first:
            # XXX: Load paths from ldso itself.
            # Remove duplicate entries to speed things up.
            paths = [p for p in dedupe(paths) if os.path.isdir(p)]

        return paths


    @functools.lru_cache()
    def load_ld_paths(root: str = '/', prefix: str = '') -> t.Dict[str, t.List[str]]:
        ldpaths: t.Dict[str, t.List[str]] = {'conf': [], 'env': [], 'interp': []}

        # Load up $LD_LIBRARY_PATH.
        env_ldpath = os.environ.get('LD_LIBRARY_PATH')
        if env_ldpath is not None:
            if root != '/':
                log.warning('ignoring LD_LIBRARY_PATH due to ROOT usage')
            else:
                # XXX: If this contains $ORIGIN, we probably have to parse this
                # on a per-ELF basis so it can get turned into the right thing.
                ldpaths['env'] = parse_ld_paths(env_ldpath, path='')

        # Load up /etc/ld.so.conf.
        ldpaths['conf'] = parse_ld_so_conf(root + prefix + '/etc/ld.so.conf',
                                        root=root)
        # the trusted directories are not necessarily in ld.so.conf
        ldpaths['conf'].extend(['/lib', '/lib64/', '/usr/lib', '/usr/lib64'])
        log.debug('linker ldpaths: %s', ldpaths)
        return ldpaths


    def compatible_elfs(elf1, elf2):
        osabis = frozenset([e.header['e_ident']['EI_OSABI'] for e in (elf1, elf2)])
        compat_sets = (frozenset('ELFOSABI_%s' % x
                                for x in ('NONE',
                                        'SYSV',
                                        'GNU',
                                        'LINUX', )), )
        return ((len(osabis) == 1 or
                any(osabis.issubset(x)
                    for x in compat_sets)) and elf1.elfclass == elf2.elfclass and
                elf1.little_endian == elf2.little_endian and
                elf1.header['e_machine'] == elf2.header['e_machine'])


    def find_lib(elf, lib, ldpaths, root='/'):
        for ldpath in ldpaths:
            path = os.path.join(ldpath, lib)
            target = readlink(path, root, prefixed=True)

            if os.path.exists(target):
                with open(target, 'rb') as f:
                    libelf = elffile.ELFFile(f)
                    if compatible_elfs(elf, libelf):
                        return (target, path)

        return (None, None)


    async def lddtree(path: str,
                root: str = '/',
                prefix: str = '',
                lookup_paths: t.Optional[t.Dict[str, t.List[str]]] = None,
                display: t.Optional[str] = None,
                lib_cache: t.Dict = {},
                _first: bool = True,
                _all_libs: t.Dict[str, t.Any] = {}) -> t.Dict[str, t.Any]:
        if _first:
            _all_libs = {}
            lookup_paths = load_ld_paths().copy()
        else:
            assert lookup_paths is not None

        ret = {
            'interp': None,
            'path': path if display is None else display,
            'realpath': path,
            'needed': [],
            'rpath': [],
            'runpath': [],
            'libs': _all_libs,
        }  # type: Dict[str, Any]

        log.debug('lddtree(%s)', path)

        with open(path, 'rb') as f:
            elf = elffile.ELFFile(f)

            # If this is the first ELF, extract the interpreter.
            if _first:
                for segment in elf.iter_segments():
                    if segment.header.p_type != 'PT_INTERP':
                        continue

                    interp = segment.get_interp_name()
                    log.debug('  interp           = %s', interp)
                    ret['interp'] = normpath(root + interp)
                    ret['libs'][os.path.basename(interp)] = {
                        'path': ret['interp'],
                        'realpath': readlink(ret['interp'],
                                            root,
                                            prefixed=True),
                        'needed': [],
                    }
                    # XXX: Should read it and scan for /lib paths.
                    lookup_paths['interp'] = [
                        normpath(root + os.path.dirname(interp)),
                        normpath(root + prefix + '/usr' + os.path.dirname(
                            interp).lstrip(prefix)),
                    ]
                    log.debug('  ldpaths[interp]  = %s', lookup_paths['interp'])
                    break

            # Parse the ELF's dynamic tags.
            libs = []  # type: List[str]
            rpaths = []  # type: List[str]
            runpaths = []  # type: List[str]
            for segment in elf.iter_segments():
                if segment.header.p_type != 'PT_DYNAMIC':
                    continue

                for t in segment.iter_tags():
                    if t.entry.d_tag == 'DT_RPATH':
                        rpaths = parse_ld_paths(
                            t.rpath,
                            root=root,
                            path=path)
                    elif t.entry.d_tag == 'DT_RUNPATH':
                        runpaths = parse_ld_paths(
                            t.runpath,
                            root=root,
                            path=path)
                    elif t.entry.d_tag == 'DT_NEEDED':
                        libs.append(t.needed)
                if runpaths:
                    # If both RPATH and RUNPATH are set, only the latter is used.
                    rpaths = []

                # XXX: We assume there is only one PT_DYNAMIC.  This is
                # probably fine since the runtime ldso does the same.
                break
            if _first:
                # Propagate the rpaths used by the main ELF since those will be
                # used at runtime to locate things.
                lookup_paths['rpath'] = rpaths
                lookup_paths['runpath'] = runpaths
                log.debug('  ldpaths[rpath]   = %s', rpaths)
                log.debug('  ldpaths[runpath] = %s', runpaths)
            ret['rpath'] = rpaths
            ret['runpath'] = runpaths
            ret['needed'] = libs

            # Search for the libs this ELF uses.
            all_ldpaths = None  # type: Optional[List[str]]
            for lib in libs:
                if lib in _all_libs:
                    continue
                cached = lib_cache.get(lib, None)
                if cached is not None:
                    _all_libs[lib] = cached
                    continue

                if all_ldpaths is None:
                    all_ldpaths = (lookup_paths['rpath'] + rpaths + runpaths +
                                lookup_paths['env'] + lookup_paths['runpath'] +
                                lookup_paths['conf'] + lookup_paths['interp'])
                realpath, fullpath = find_lib(elf, lib, all_ldpaths, root)
                _all_libs[lib] = {
                    'realpath': realpath,
                    'path': fullpath,
                    'needed': [],
                }
                if fullpath:
                    lret = await lddtree(realpath,
                                root,
                                prefix,
                                lookup_paths,
                                display=fullpath,
                                lib_cache=lib_cache,
                                _first=False,
                                _all_libs=_all_libs)
                    _all_libs[lib]['needed'] = lret['needed']

            del elf

        return ret

    async def dep_list(path, lookup_dirs):
        tree = await lddtree(path, lookup_paths=lookup_dirs)
        result = list()
        for lib, data in tree['libs'].items():
            result.append((lib, data['realpath']))
        return result

async def get_runtime_dependencies(t : Executable|Library):
    lookup_dirs = t.env['PATH'].split(os.pathsep)
    return await dep_list(t.output, lookup_dirs)
