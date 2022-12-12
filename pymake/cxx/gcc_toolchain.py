import asyncio
from functools import cached_property
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
        flags = set()
        if self.env:
            if 'SYSROOT' in self.env:
                flags.add(f'--sysroot={self.env["SYSROOT"]}')
            if 'CFLAGS' in self.env:
                flags.update(self.env["CFLAGS"].strip().split(' '))
        return flags

    @cached_property
    def default_cxxflags(self):
        flags = {f'-std=c++{self.cpp_std}'}
        if self.env:
            if 'CXXFLAGS' in self.env:
                flags.update(self.env["CXXFLAGS"].strip().split(' '))
        return flags
    
    @cached_property
    def default_ldflags(self):
        flags = set()
        if self.env:
            if 'LDFLAGS' in self.env:
                flags.update(self.env["LDFLAGS"].strip().split(' '))
        return flags

    def set_mode(self, mode: str):
        if mode == 'debug':
            self.default_cflags.update(('-g', ))
        elif mode == 'release':
            self.default_cflags.update(('-O3', '-DNDEBUG'))
        elif mode == 'release-min-size':
            self.default_cflags.update(('-Os', '-DNDEBUG'))
        elif mode == 'release-debug-infos':
            self.default_cflags.update(('-O2', '-g', '-DNDEBUG'))
        else:
            raise InvalidConfiguration(f'unknown build mode: {mode}')

    def has_cxx_compile_options(self, *opts) -> bool:
        _, err, _ = asyncio.run(
            self.run(f'{self.cxx} {" ".join(opts)}', no_raise=True))
        return err.splitlines()[0].find('no input files') >= 0

    def make_include_options(self, include_paths: set[Path]) -> set[str]:
        return {f'-I{p}' for p in include_paths}

    def make_link_options(self, libraries: set[Path | str]) -> set[str]:
        opts = set()
        for lib in libraries:
            if isinstance(lib, Path):
                opts.add(f'-L{lib.parent}')
                opts.add(f'-Wl,-rpath,{lib.parent}')
                opts.add(f'-l{lib.stem.removeprefix("lib")}')
            else:
                assert isinstance(lib, str)
                opts.add(f'-l{lib}')
        return opts

    def make_compile_definitions(self, definitions: set[str]) -> set[str]:
        return {f'-D{d}' for d in definitions}

    async def scan_dependencies(self, file: Path, options: set[str], build_path:Path) -> set[FileDependency]:
        if not scan:
            return set()

        build_path.mkdir(parents=True, exist_ok=True)
        output = build_path / file.name
        out, _, _ = await self.run('scan', output, [self.cxx, '-M', file, *unique(self.default_cflags, self.default_cxxflags, options)], cwd=build_path)
        if out:
            all = ''.join([dep.replace('\\', ' ')
                        for dep in out.splitlines()]).split()
            _obj = all.pop(0)
            _src = all.pop(0)
            return {FileDependency(dep) for dep in all}
        else:
            return set()

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {output.with_suffix(output.suffix + '.d')}

    @property
    def cxxmodules_flags(self) -> set[str]:
        return {'-std=c++20', '-fmodules-ts'}

    async def compile(self, sourcefile: Path, output: Path, options: set[str]):
        args = [*unique(self.default_cflags, self.default_cxxflags, options), '-MD', '-MT',
                str(output), '-MF', f'{output}.d', '-o', str(output), '-c', str(sourcefile)]
        if auto_fpic:
            args.insert(0, '-fPIC')
        args.insert(0, self.cxx)
        self.compile_commands.insert(sourcefile, output.parent, args)
        await self.run('cc', output, args)

    async def link(self, objects: set[Path], output: Path, options: set[str]):
        args = [self.cxx, *objects, '-o', output, *unique(self.default_ldflags, self.default_cflags, self.default_cxxflags, options)]
        await self.run('link', output, args)

    async def static_lib(self, objects: set[Path], output: Path, options: set[str] = set()):
        await self.run('static_lib', output, [self.ar, 'qc', output, *objects])
        await AsyncRunner.run(self, [self.ranlib, output])

    async def shared_lib(self, objects: set[Path], output: Path, options: set[str] = set()):
        await self.run('shared_lib', output, [self.cxx, '-shared', *unique(self.default_ldflags, options), *objects, '-o', output])
