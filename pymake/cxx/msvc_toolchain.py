import json

import aiofiles
from pymake.core.runners import sync_run
from pymake.core.settings import BuildType
from pymake.core.utils import unique
from pymake.cxx.toolchain import CommandArgsList, RuntimeType, Toolchain, Path, FileDependency, scan
from pymake.core.errors import InvalidConfiguration
from pymake.core.pm import re_match


class MSVCToolchain(Toolchain):
    def __init__(self, data, tools):
        Toolchain.__init__(self, data)
        self.cc = Path(data['cc'])
        self.cxx = self.cc
        self.lnk = Path(data['link'])
        self.lib = Path(data['lib'])
        self.env = data['env']

    @property
    def default_cflags(self):
        rt = '/MD' if self.runtime == RuntimeType.dynamic else '/MT'
        if self.build_type == BuildType.debug:
            rt += 'd'
        return [
            '/nologo',
            '/EHsc',
            '/GA',
            rt,
        ]

    @property
    def default_cxxflags(self):
        return [f'/std:c++{self.cpp_std}']

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
        lib_paths = list()
        libs = list()
        for lib in libraries:
            if isinstance(lib, Path):
                lib_paths.append(f'/LIBPATH:{lib.parent}')
                libs.append(f'{lib.stem}.lib')
            else:
                assert isinstance(lib, str)
                libs.append(f'{lib}.lib')
        return [*libs, *lib_paths]

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        return [f'/D{d}' for d in definitions]

    def make_library_name(self, basename: str, shared: bool) -> str:
        return f'{basename}.{"dll" if shared else "lib"}'

    def make_executable_name(self, basename: str) -> str:
        return f'{basename}.exe'
    
    def from_unix_flags(self, flags: list[str]):
        out = list()
        for flag in flags:
            flag = flag.replace('"', '')
            match re_match(flag):
                case r'-L(.+)' as m:
                    out.append(f'/LIBPATH:{m[1]}')
                case r'-l(.+)' as m:
                    out.append(f'{m[1]}.lib')
                case r'-I(.+)' as m:
                    out.append(f'/I{m[1]}')
                case _:
                    out.append(flag)
        return out

    def to_unix_flags(self, flags: list[str]):
        out = list()
        for flag in flags:
            flag = flag.replace('"', '')
            match re_match(flag):
                case r'/LIBPATH:(.+)' as m:
                    out.append(f'-L{m[1]}')
                case r'(.+).lib' as m:
                    out.append(f'-l{m[1]}')
                case r'/I(.+)' as m:
                    out.append(f'-I{m[1]}')
                case _:
                    out.append(flag)
        return out

    async def scan_dependencies(self, file: Path, options: list[str], build_path: Path) -> set[FileDependency]:
        return set()
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

    def make_compile_commands(self, sourcefile: Path, output: Path, options: list[str]) -> CommandArgsList:
        args = [self.cc, *unique(self.default_cflags, self.default_cxxflags, options),
                f'/Fo{str(output)}', '/c', str(sourcefile)]
        return [args]

    def make_link_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        return [[self.lnk, '/nologo', *options, *objects, f'/OUT:{str(output)}']]

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        objects = list(objects)
        objs = [objects[0].name]
        for obj in objects[1:]:
            objs.append(obj.name)
        return [[self.lib, '/nologo', *objs, f'/OUT:{output}']]

    def make_shared_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        objects = list(objects)
        objs = [objects[0].name]
        for obj in objects[1:]:
            objs.append(obj.name)
        return [[self.lnk, '/nologo',
                f'/IMPLIB:{output.with_suffix(".lib")}', '/DLL', *options, *objs, f'/OUT:{output.with_suffix(".dll")}']]
