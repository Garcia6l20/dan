from functools import cached_property
from dan.core import aiofiles, diagnostics as diag
from dan.core.pm import re_match
from dan.core.settings import BuildType
from dan.core.utils import unique, Environment
from dan.cxx.base_toolchain import CommandArgsList, Toolchain, Path, FileDependency, CppStd
from dan.core.runners import sync_run

import typing as t

cxx_extensions = ['.cpp', '.cxx', '.C', '.cc']
c_extensions = ['.c']
asm_extensions = ['.s', 'S']

def get_in(key, *dicts):
    for d in dicts:
        if key in d:
            return d[key]

class UnixToolchain(Toolchain):

    vendors = ['gcc', 'clang']

    __tools = [
        ('cc', 'cc', 'CC'),
        ('cxx', 'cxx', 'CC'),
        ('ar', 'ar', 'AR'),
        ('objcopy', 'objcopy', 'OBJCOPY'),
        ('ranlib', 'ranlib', 'RANLIB'),
        ('as', '_as', 'AS'),
        ('strip', 'strip', 'STRIP'),
        ('nm', 'nm', 'NM'),
    ]
    
    def __setup_tools(self):
        for data_name, self_name, env_name in self.__tools:
            item = get_in(data_name, self.data, self.tools)
            setattr(self, self_name, Path(item) if item else None)
            if item is not None:
                self.env[env_name] = str(item)
    
    def __init__(self, *args, **kwargs):
        Toolchain.__init__(self, *args, **kwargs)
        self.cc = Path(self.data['cc'])
        self.cxx = Path(self.data['cxx'])
        env = self.data['env'] if 'env' in self.data else None
        self.env = Environment(env)
        self.env.path_prepend(self.cc.parent)
        self.env['CC'] = str(self.cc)
        self.env['CXX'] = str(self.cxx)
        self.__setup_tools()
    
        self.debug('C compiler is %s %s (%s)',
                   self.type, self.version, self.cc)
        self.debug('C++ compiler is %s %s (%s)',
                   self.type, self.version, self.cxx)

    def get_optimization_flags(self, build_type):
        flags = list()
        if build_type is None:
            build_type = self.build_type
        match build_type:
            case BuildType.debug:
                flags.extend(('-g', ))
            case BuildType.release:
                flags.extend(('-O3', '-DNDEBUG'))
            case BuildType.release_min_size:
                flags.extend(('-Os', '-DNDEBUG'))
            case BuildType.release_debug_infos:
                flags.extend(('-O2', '-g', '-DNDEBUG'))
        return flags

    @cached_property
    def default_cflags(self):
        flags = list()
        if self.env:
            if 'SYSROOT' in self.env:
                flags.append(f'--sysroot={self.env["SYSROOT"]}')
            if 'CFLAGS' in self.env:
                flags.extend(self.env["CFLAGS"].strip().split(' '))
        return unique(flags)

    @cached_property
    def default_cxxflags(self):
        flags = list()
        if self.env:
            if 'CXXFLAGS' in self.env:
                flags.extend(self.env["CXXFLAGS"].strip().split(' '))
        return unique(flags)

    @cached_property
    def default_ldflags(self):
        flags = list()
        if self.env:
            if 'LDFLAGS' in self.env:
                flags.extend(self.env["LDFLAGS"].strip().split(' '))
        return unique(flags)

    def has_cxx_compile_options(self, *opts) -> bool:
        _, err, _ = sync_run([self.cxx, *opts], no_raise=True)
        return err.splitlines()[0].find('no input files') >= 0

    def make_include_options(self, include_paths: set[Path]) -> list[str]:
        return unique([f'-I{p}' for p in include_paths])

    def make_libpath_options(self, libraries: set[Path | str]) -> list[str]:
        opts = list()
        if self.rpath:
            opts.append(f'-Wl,-rpath,{self.rpath}')

        for lib in libraries:
            if isinstance(lib, Path):
                opts.append(f'-L{lib.parent}')
                if not self.rpath:
                    opts.append(f'-Wl,-rpath,{lib.parent}')
        return opts

    def make_link_options(self, libraries: set[Path | str]) -> list[str]:
        opts = list(self.settings.link_flags)
        for lib in libraries:
            if isinstance(lib, Path):
                opts.append(f'-l{lib.stem.removeprefix("lib")}')
            else:
                assert isinstance(lib, str)
                opts.append(f'-l{lib}')
        return opts

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        return unique([f'-D{d}' for d in definitions])

    def make_compile_options(self, options: set[str]) -> list[str]:
        result = list(self.settings.compile_flags)
        for o in options:
            match o:
                case CppStd():
                    result.append(f'-std=c++{o.stdver}')
                case _:
                    result.append(o)
        return result

    def make_library_name(self, basename: str, shared: bool) -> str:
        if not shared:
            if self.settings.archive_extension is not None:
                return f'{basename}.{self.settings.archive_extension}'
            return f'lib{basename}.a'
        elif self.settings.library_extension is not None:
                return f'{basename}.{self.settings.library_extension}'
        elif self.system.is_windows:
            return f'lib{basename}.dll'
        else:
            return f'lib{basename}.so'

    def make_executable_name(self, basename: str) -> str:
        if self.settings.executable_extension is not None:
            return f'{basename}.{self.settings.executable_extension}'
        return f'{basename}.exe' if self.system.is_windows else basename

    def get_base_compile_args(self, sourcefile: Path, build_type) -> list[str]:
        match sourcefile.suffix:
            case _ if sourcefile.suffix in cxx_extensions:
                return [self.cxx, *self.default_cxxflags, *self.get_optimization_flags(build_type), *self.default_cflags]
            case _ if sourcefile.suffix in c_extensions:
                return [self.cc, *self.default_cxxflags, *self.get_optimization_flags(build_type), *self.default_cflags]
            case _ if sourcefile.suffix in asm_extensions:
                return [self.cc, *self.default_cxxflags, *self.get_optimization_flags(build_type), *self.default_cflags]
            case _:
                raise RuntimeError(
                    f'Unhandled source file extention: {sourcefile.suffix}')

    async def scan_dependencies(self, sourcefile: Path, output: Path, options: set[str]) -> set[FileDependency]:
        deps_path = output.with_suffix(".o.d")
        deps = list()
        if deps_path.exists():
            async with aiofiles.open(deps_path, 'r') as f:
                for dep in await f.readlines():
                    dep = dep.strip()
                    if dep.endswith('\\'):
                        dep = dep[:-2]
                    deps.append(dep.strip())
                _obj = deps.pop(0)
                if len(deps) > 0:
                    _src = deps.pop(0)
        return set(deps)

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {output.with_suffix(output.suffix + '.d')}

    @property
    def cxxmodules_flags(self) -> list[str]:
        return ['-std=c++20', '-fmodules-ts']

    def make_compile_commands(self, sourcefile: Path, output: Path, options: set[str], build_type=None) -> CommandArgsList:
        args = self.get_base_compile_args(sourcefile, build_type)
        args.extend([*self.compile_options, *options, '-MD', '-MT', str(output),
                    '-MF', f'{output}.d', '-o', str(output), '-c', str(sourcefile)])
        if self.settings.position_independent_code:
            args.insert(1, '-fPIC')
        return [args]

    def make_link_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        args = [self.cxx, *objects, '-o', str(output), *unique(
            self.default_ldflags, self.default_cflags, self.default_cxxflags, self.link_options, options)]
        commands = [args]
        if self.build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.objcopy, '-S', output, output])
        return commands

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        return [
            [self.ar, 'cr', output, *objects],  # *options],
            [self.ranlib, output],
        ]

    def make_shared_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> tuple[Path, CommandArgsList]:
        args = [self.cxx, '-shared', *objects, *
                unique(self.default_ldflags, options), '-o', output]
        commands = [args]
        if self.build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.objcopy, '-S', output, output])
        return commands

    async def get_default_include_paths(self, lang='c++') -> list[Path]:
        cache_key = f'default_{lang}_includes'
        includes = self.cache.get(cache_key, None)
        if includes is None:
            args = [self.cc, '-x', lang, '-E', '-Wp,-v', '-']
            out, err, rc = await self.run(f'get default {lang} includes', None, args, quiet=True, log=False, input='')
            if rc != 0:
                self.error('failed to get default %s includes: %s', lang, err)
                return []
            includes = []
            for line in [*out.splitlines(), *err.splitlines()]:
                match re_match(line):
                    case r'^ (.+)$' as m:
                        includes.append(str(Path(m[1]).resolve()))
            self.cache[cache_key] = includes
        return includes

    async def _gen_gcc_compile_diags(self, lines) -> t.Iterable[diag.Diagnostic]:
        _from = list()
        prev: diag.Diagnostic | diag.RelatedInformation = None
        prev_diag: diag.Diagnostic = None
        async for line in lines:
            match re_match(line):
                case r'\s+?\|\s(\s+)?(\^~+)' as m:
                    if prev is not None:
                        if isinstance(prev, diag.Diagnostic):
                            rng = prev.range
                        else:
                            rng = prev.location.range
                        rng.start.character = len(m[1]) if m[1] else 0
                        rng.end.character = rng.start.character + len(m[2])
                case r'((?:.+)from (.+)):(\d+)[,:]' as m:
                    message = m[1]
                    if message.startswith('In file included'):
                        _from.clear()
                    filename = m[2]
                    lineno = int(m[3]) - 1
                    prev = info = diag.RelatedInformation(
                        location=diag.Location(diag.Uri(filename),
                                               range=diag.Range(start=diag.Position(lineno), end=diag.Position(lineno))),
                        message=message)
                    _from.append(info)
                case r'(.+?): In instantiation of \'(.+)\'' as m:
                    _from.clear()
                case r'(.+?):(\d+):(?:(\d+):)?\s+(required from\s.+)' as m:
                    filename = m[1]
                    lineno = int(m[2]) - 1
                    character = int(m[3]) - 1 if m[3] else 0
                    message = m[4]
                    prev = info = diag.RelatedInformation(
                        location=diag.Location(diag.Uri(filename),
                                               range=diag.Range(start=diag.Position(lineno, character), end=diag.Position(lineno, character))),
                        message=message)
                    _from.append(info)
                case r'(.+?):(\d+):(?:(\d+):)?\s(note):\s(.+)$' as m:
                    filename = m[1]
                    character = int(m[3]) if m[3] else 0
                    lineno = int(m[2]) - 1
                    message = m[5]
                    if prev_diag is None:
                        self.warning(
                            'diagnostics: a note is expected to append after a diagnositc')
                    else:
                        info = diag.RelatedInformation(
                            location=diag.Location(diag.Uri(filename),
                                                   range=diag.Range(start=diag.Position(lineno, character), end=diag.Position(lineno, character))),
                            message=message)
                        prev_diag.related_information.insert(0, info)
                        prev = info
                case r'(.+?):(\d+):(?:(\d+):)?\s(?:fatal )?(error|warning):\s(.+)$' as m:
                    character = int(m[3]) if m[3] else 0
                    lineno = int(m[2]) - 1
                    message = m[5]
                    prev_diag = prev = diag.Diagnostic(
                        message=message,
                        range=diag.Range(start=diag.Position(
                            line=lineno, character=character), end=diag.Position(line=lineno)),
                        severity=diag.Severity[m[4].upper()],
                        source=self.type,
                        filename=m[1],
                        related_information=list(_from)
                    )
                    yield prev_diag

    async def _handle_compile_output(self, lines) -> t.Iterable[diag.Diagnostic]:
        match self.type:
            case 'gcc' | 'clang':
                async for d in self._gen_gcc_compile_diags(lines):
                    yield d
            case _:
                raise NotImplementedError(
                    f'handle_compile_output errors not implemented for {self.type}')

    async def _gen_ld_link_diags(self, lines) -> t.Iterable[diag.Diagnostic]:
        function = None
        object = None
        async for line in lines:
            match re_match(line):
                case r'(.+): in function `(.+)\':$' as m:
                    object = m[1]
                    function = m[2]
                case r'(?:.+: )?(?:(.+):)?\((.+)\+(.+)\): (.+)$' as m:
                    # link error may not be associated to a source file,
                    # in which case the associated file is the object
                    filename = m[1] or object
                    section = m[2]
                    section_offset = int(m[3], 0)
                    message = m[4].strip()
                    yield diag.Diagnostic(
                        message=message,
                        source=self.type
                    )
                case r'(?:.+?: )?(.+?):(\d+): (undefined reference to.+)$' as m:
                    filename = m[1]
                    line = int(m[2])
                    message = m[3].strip()
                    yield diag.Diagnostic(
                        message=message,
                        filename=filename,
                        range=diag.Range(start=diag.Position(line=line)),
                        source=self.type
                    )
                case _:
                    self._logger.debug('unhandled line: %s', line)

    async def _handle_link_output(self, lines) -> t.Iterable[diag.Diagnostic]:
        match self.type:
            case 'gcc' | 'clang':
                async for d in self._gen_ld_link_diags(lines):
                    yield d
            case _:
                raise NotImplementedError(
                    f'handle_link_output not implemented for {self.type}')
