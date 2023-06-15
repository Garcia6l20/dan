from functools import cached_property
from dan.core import diagnostics as diag
from dan.core.pm import re_match
from dan.core.settings import BuildType
from dan.core.utils import unique
from dan.cxx.toolchain import CommandArgsList, Toolchain, Path, FileDependency
from dan.cxx import auto_fpic
from dan.core.runners import sync_run

import typing as t

cxx_extensions = ['.cpp', '.cxx', '.C', '.cc']
c_extensions = ['.c']


class UnixToolchain(Toolchain):
    def __init__(self, data, tools, *args, **kwargs):
        Toolchain.__init__(self, data, tools, *args, **kwargs)
        self.cc = data['cc']
        self.cxx = data['cxx']
        self.ar = data['ar'] if 'ar' in data else tools['ar']
        self.ranlib = data['ranlib'] if 'ranlib' in data else tools['ranlib']
        # self.as_ = data['as'] if 'as' in data else tools['as']
        # self.strip = data['env']['STRIP'] if 'env' in data and 'STRIP' in data['env'] else tools['strip']
        self.env = data['env'] if 'env' in data else None
        self.debug('cxx compiler is %s %s (%s)', self.type, self.version, self.cc)
        self.debug('cxx compiler is %s %s (%s)', self.type, self.version, self.cxx)

    @cached_property
    def default_cflags(self):
        flags = list()
        match self.build_type:
            case BuildType.debug:
                flags.extend(('-g', ))
            case BuildType.release:
                flags.extend(('-O3', '-DNDEBUG'))
            case BuildType.release_min_size:
                flags.extend(('-Os', '-DNDEBUG'))
            case BuildType.release_debug_infos:
                flags.extend(('-O2', '-g', '-DNDEBUG'))
        if self.env:
            if 'SYSROOT' in self.env:
                flags.append(f'--sysroot={self.env["SYSROOT"]}')
            if 'CFLAGS' in self.env:
                flags.extend(self.env["CFLAGS"].strip().split(' '))
        return unique(flags)

    @cached_property
    def default_cxxflags(self):
        flags = [f'-std=c++{self.cpp_std}', *self.settings.cxx_flags]
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

    def make_link_options(self, libraries: set[Path | str]) -> list[str]:
        opts = list()
        if self.rpath:
            opts.append(f'-Wl,-rpath,{self.rpath}')

        for lib in libraries:
            if isinstance(lib, Path):
                opts.append(f'-L{lib.parent}')
                if not self.rpath:
                    opts.append(f'-Wl,-rpath,{lib.parent}')
                opts.append(f'-l{lib.stem.removeprefix("lib")}')
            else:
                assert isinstance(lib, str)
                opts.append(f'-l{lib}')
        return unique(opts)

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        return unique([f'-D{d}' for d in definitions])

    def make_library_name(self, basename: str, shared: bool) -> str:
        return f'lib{basename}.{"so" if shared else "a"}'

    def make_executable_name(self, basename: str) -> str:
        return f'{basename}.exe' if self.system.startswith('msys') else basename

    def get_base_compile_args(self, sourcefile: Path) -> list[str]:
        match sourcefile.suffix:
            case _ if sourcefile.suffix in cxx_extensions:
                return [self.cxx, *self.default_cxxflags]
            case _ if sourcefile.suffix in c_extensions:
                return [self.cc, *self.default_cflags]
            case _:
                raise RuntimeError(
                    f'Unhandled source file extention: {sourcefile.suffix}')

    async def scan_dependencies(self, sourcefile: Path, options: list[str], build_path: Path) -> set[FileDependency]:
        args = self.get_base_compile_args(sourcefile)
        args.extend(['-M', str(sourcefile), *options])

        if auto_fpic:
            args.insert(1, '-fPIC')

        build_path.mkdir(parents=True, exist_ok=True)
        output = build_path / sourcefile.name
        out, _, _ = await self.run('scan', output, args, log=False, cwd=build_path)
        if out:
            all = ''.join([dep.replace('\\', ' ')
                           for dep in out.splitlines()]).split()
            _obj = all.pop(0)
            _src = all.pop(0)
            return all
        else:
            return set()

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {output.with_suffix(output.suffix + '.d')}

    @property
    def cxxmodules_flags(self) -> list[str]:
        return ['-std=c++20', '-fmodules-ts']
    
    def make_compile_commands(self, sourcefile: Path, output: Path, options: set[str]) -> CommandArgsList:
        args = self.get_base_compile_args(sourcefile)
        args.extend([*self.compile_options, *options, '-MD', '-MT', str(output),
                    '-MF', f'{output}.d', '-o', str(output), '-c', str(sourcefile)])
        if auto_fpic:
            args.insert(1, '-fPIC')
        return [args]

    def make_link_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        args = [self.cxx, *[o.name for o in objects], '-o', str(output), *unique(
            self.default_ldflags, self.default_cflags, self.default_cxxflags, self.link_options, options)]
        commands = [args]
        if self._build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.strip, output])
        return commands

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        return [
            [self.ar, 'cr', output, *[o.name for o in objects]], # *options],
            [self.ranlib, output],
        ]

    def make_shared_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        args = [self.cxx, '-shared', *
                unique(self.default_ldflags, options), *objects, '-o', output]
        commands = [args]
        if self._build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.strip, output])
        return commands
    
    async def get_default_include_paths(self, lang = 'c++') -> list[Path]:
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
        async for line in lines:
            match re_match(line):
                case r'(.+):(\d+):(\d+):\s(error|warning):\s(.+)$' as m:
                    yield diag.Diagnostic(
                        message=m[5],
                        range=diag.Range(start=diag.Position(line=int(m[2])-1, character=int(m[3]))),
                        severity=diag.Severity[m[4].upper()],
                        source=self.type,
                        filename=m[1]
                    )

    async def _handle_compile_output(self, lines) -> t.Iterable[diag.Diagnostic]:
        match self.type:
            case 'gcc'|'clang':
                async for d in self._gen_gcc_compile_diags(lines):
                    yield d
            case _:
                raise NotImplementedError(f'handle_compile_output errors not implemented for {self.type}')
    
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
                    message = m[4]
                    yield diag.Diagnostic(
                        message=message,
                        source=self.type
                    )
                case _:
                    self._logger.debug('unhandled line: %s', line)

    async def _handle_link_output(self, lines) -> t.Iterable[diag.Diagnostic]:
        match self.type:
            case 'gcc'|'clang':
                async for d in self._gen_ld_link_diags(lines):
                    yield d
            case _:
                raise NotImplementedError(f'handle_link_output not implemented for {self.type}')
