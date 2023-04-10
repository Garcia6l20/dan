import asyncio
import json

import aiofiles
from pymake.core.runners import sync_run
from pymake.core.settings import BuildType
from pymake.core.utils import unique
from pymake.cxx.toolchain import Toolchain, Path, FileDependency, scan
from pymake.core.errors import InvalidConfiguration


class MSVCToolchain(Toolchain):
    def __init__(self, data, tools):
        Toolchain.__init__(self, data)
        self.cc = Path(data['cc'])
        self.cxx = self.cc
        self.lnk = Path(data['link'])
        self.lib = Path(data['lib'])
        self.env = data['env']
        self.default_cflags = ['/nologo', '/EHsc', '/GA', '/MT']
        self.default_cxxflags = [f'/std:c++{self.cpp_std}']

    @Toolchain.build_type.setter
    def build_type(self, mode: BuildType):
        self._build_type = mode
        if mode == BuildType.debug:
            pass
        elif mode == BuildType.release:
            self.default_cflags.extend(('/O2', '/DNDEBUG'))
        elif mode == BuildType.release_min_size:
            self.default_cflags.extend(('/Os', '/DNDEBUG'))
        elif mode == BuildType.release_debug_infos:
            self.default_cflags.extend(('/O2', '/DNDEBUG'))
        else:
            raise InvalidConfiguration(f'unknown build mode: {mode}')

    def has_cxx_compile_options(self, *opts) -> bool:
        _, err, _ = sync_run([self.cxx, *opts], no_raise=True)
        # D9002 => unknown option
        return err.splitlines()[0].find('D9002') == 0

    def make_include_options(self, include_paths: set[Path]) -> list[str]:
        return [f'/I{p}' for p in include_paths]

    def make_link_options(self, libraries: set[Path | str]) -> list[str]:
        opts = list()
        for lib in libraries:
            if isinstance(lib, Path):
                opts.append(f'/LIBPATH:{lib.parent}')
                opts.append(f'{lib.stem}.lib')
            else:
                assert isinstance(lib, str)
                opts.append(f'{lib}.lib')
        return opts

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        return [f'/D{d}' for d in definitions]

    def make_library_name(self, basename: str, shared: bool) -> str:
        return f'{basename}.{"dll" if shared else "lib"}'

    def make_executable_name(self, basename: str) -> str:
        return f'{basename}.exe'

    async def scan_dependencies(self, file: Path, options: list[str], build_path: Path) -> set[FileDependency]:
        if not scan:
            return set()

        build_path.mkdir(parents=True, exist_ok=True)
        desc = build_path / file.with_suffix(".json").name
        args = [self.cc,
                *unique(self.default_cflags, self.default_cxxflags, options),
                '/scanDependencies', desc, file]
        await self.run('scan', desc, args,
                       cwd=build_path)
        deps = set()
        async with aiofiles.open(desc, 'r') as f:
            data = json.loads(await f.read())
            for rule in data['rules']:
                for req in rule['requires']:
                    if 'source-path' in req:
                        deps.add(FileDependency(req['source-path']))
        return deps

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {}

    @property
    def cxxmodules_flags(self) -> list[str]:
        return list()

    async def compile(self, sourcefile: Path, output: Path, options: list[str], dry_run=False, compile_commands=True, **kwargs):
        args = [self.cc, *unique(self.default_cflags, self.default_cxxflags, options),
                f'/Fo{str(output)}', '/c', str(sourcefile)]
        if compile_commands:
            self.compile_commands.insert(sourcefile, output.parent, args)
        if not dry_run:
            await self.run('cc', output, args, **kwargs)
        return args

    async def link(self, objects: set[Path], output: Path, options: list[str]):
        args = [self.lnk, '/nologo', *options, *objects, f'/OUT:{str(output)}']
        await self.run('link', output, args)
        return args

    async def static_lib(self, objects: set[Path], output: Path, options: list[str] = list()):
        objects = list(objects)
        cwd = objects[0].parent
        objs = [objects[0].name]
        for obj in objects[1:]:
            assert obj.parent == cwd
            objs.append(obj.name)
        args = [self.lib, '/nologo', *objs, f'/OUT:{output}']
        await self.run('static_lib', output, args, cwd=cwd)
        return args

    async def shared_lib(self, objects: set[Path], output: Path, options: list[str] = list()):
        objects = list(objects)
        cwd = objects[0].parent
        objs = [objects[0].name]
        for obj in objects[1:]:
            assert obj.parent == cwd
            objs.append(obj.name)
        args = [self.lnk, '/nologo',
                f'/IMPLIB:{output.with_suffix(".lib")}', '/DLL', *options, *objs, f'/OUT:{output.with_suffix(".dll")}']
        await self.run('shared_lib', output, args)
        return args
