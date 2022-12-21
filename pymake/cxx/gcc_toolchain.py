import asyncio
from functools import cached_property
from pymake.core.settings import BuildType
from pymake.logging import Logging
from pymake.core.utils import AsyncRunner, unique
from pymake.cxx.toolchain import Toolchain, Path, FileDependency, scan
from pymake.core.errors import InvalidConfiguration
from pymake.cxx import auto_fpic


class GCCToolchain(Toolchain):
    def __init__(self, data, tools):
        Toolchain.__init__(self)
        Logging.__init__(self, 'gcc-toolchain')
        self.cc = data['cc']
        self.cxx = data['cxx']        
        self.ar = data['ar'] if 'ar' in data else tools['ar']
        self.ranlib = data['ranlib'] if 'ranlib' in data else tools['ranlib']
        self.as_ = data['readelf'] if 'readelf' in data else tools['readelf']
        self.env = data['env'] if 'env' in data else None
    
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
        flags = [f'-std=c++{self.cpp_std}']
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

    def set_rpath(self, rpath : str):
        self.rpath = rpath

    @Toolchain.build_type.setter
    def build_type(self, mode: BuildType):
        self._build_type = mode
        if mode == BuildType.debug:
            self.default_cflags.extend(('-g', ))
        elif mode == BuildType.release:
            self.default_cflags.extend(('-O3', '-DNDEBUG'))
        elif mode == BuildType.release_min_size:
            self.default_cflags.extend(('-Os', '-DNDEBUG'))
        elif mode == BuildType.release_debug_infos:
            self.default_cflags.extend(('-O2', '-g', '-DNDEBUG'))
        else:
            raise InvalidConfiguration(f'unknown build mode: {mode}')

    def has_cxx_compile_options(self, *opts) -> bool:
        _, err, _ = asyncio.run(
            self.run(f'{self.cxx} {" ".join(opts)}', no_raise=True))
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

    async def scan_dependencies(self, file: Path, options: list[str], build_path:Path) -> set[FileDependency]:
        if not scan:
            return set()
        args = [self.cxx, '-M', file, *unique(self.default_cflags, self.default_cxxflags, options)]
        if auto_fpic:
            args.insert(2, '-fPIC')

        build_path.mkdir(parents=True, exist_ok=True)
        output = build_path / file.name
        out, _, _ = await self.run('scan', output, args, cwd=build_path)
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

    async def compile(self, sourcefile: Path, output: Path, options: list[str], dry_run=False):
        args = [*unique(self.default_cflags, self.default_cxxflags, options), '-MD', '-MT',
                str(output), '-MF', f'{output}.d', '-o', str(output), '-c', str(sourcefile)]
        if auto_fpic:
            args.insert(0, '-fPIC')
        args.insert(0, self.cxx)
        self.compile_commands.insert(sourcefile, output.parent, args)
        if not dry_run:
            await self.run('cc', output, args)
        return args

    async def link(self, objects: set[Path], output: Path, options: list[str], dry_run=False):
        args = [self.cxx, *objects, '-o', str(output), *unique(self.default_ldflags, self.default_cflags, self.default_cxxflags, options)]
        if not dry_run:
            await self.run('link', output, args)
        return args

    async def static_lib(self, objects: set[Path], output: Path, options: list[str] = list(), dry_run=False):
        args = [self.ar, 'qc', output, *objects]
        if not dry_run:
            await self.run('static_lib', output, args)
            await AsyncRunner.run(self, [self.ranlib, output])
        return args

    async def shared_lib(self, objects: set[Path], output: Path, options: list[str] = list(), dry_run=False):
        args = [self.cxx, '-shared', *unique(self.default_ldflags, options), *objects, '-o', output]
        if not dry_run:
            await self.run('shared_lib', output, args)
        return args
