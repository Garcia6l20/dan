from functools import cached_property
from dan.core.settings import BuildType, ToolchainSettings
from dan.core.utils import unique
from dan.cxx.toolchain import CommandArgsList, Toolchain, Path, FileDependency
from dan.cxx import auto_fpic
from dan.core.runners import sync_run

cxx_extensions = ['.cpp', '.cxx', '.C', '.cc']
c_extensions = ['.c']


class UnixToolchain(Toolchain):
    def __init__(self, data, tools, *args, **kwargs):
        Toolchain.__init__(self, data, tools, *args, **kwargs)
        self.cc = data['cc']
        self.cxx = data['cxx']
        self.ar = data['ar'] if 'ar' in data else tools['ar']
        self.ranlib = data['ranlib'] if 'ranlib' in data else tools['ranlib']
        self.as_ = data['readelf'] if 'readelf' in data else tools['readelf']
        self.strip = data['env']['STRIP'] if 'env' in data and 'STRIP' in data['env'] else tools['strip']
        self.env = data['env'] if 'env' in data else None
        self.debug(f'cc compiler is {self.type} {self.version} ({self.cc})')
        self.debug(f'cxx compiler is {self.type} {self.version} ({self.cxx})')

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
        return basename

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
        args = [self.cxx, *objects, '-o', str(output), *unique(
            self.default_ldflags, self.default_cflags, self.default_cxxflags, self.link_options, options)]
        commands = [args]
        if self._build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.strip, output])
        return commands

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        return [
            [self.ar, 'cr', output, *objects], # *options],
            [self.ranlib, output],
        ]

    def make_shared_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        args = [self.cxx, '-shared', *
                unique(self.default_ldflags, options), *objects, '-o', output]
        commands = [args]
        if self._build_type in [BuildType.release, BuildType.release_min_size]:
            commands.append([self.strip, output])
        return commands
