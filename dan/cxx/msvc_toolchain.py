from functools import cached_property
import json

import aiofiles
from dan.core.runners import sync_run
from dan.core.settings import BuildType
from dan.core.utils import unique
from dan.cxx.toolchain import CommandArgsList, RuntimeType, Toolchain, Path, FileDependency
from dan.core.pm import re_match


class MSVCToolchain(Toolchain):
    def __init__(self, data, *args, **kwargs):
        Toolchain.__init__(self, data, *args, **kwargs)
        self.cc = Path(data['cc'])
        self.cxx = self.cc
        self.lnk = Path(data['link'])
        self.lib = Path(data['lib'])
        self.env = data['env']
    
    @cached_property
    def common_flags(self):
        flags = [
            '/nologo',
        ]
        if self.build_type.is_debug_mode:
            flags.append('/DEBUG')
        return flags

    @cached_property
    def default_cflags(self):
        flags = [
            '/EHsc',
            '/GA',
        ]
        rt = '/MD' if self.runtime == RuntimeType.dynamic else '/MT'
        match self.build_type:
            case BuildType.debug:
                flags.extend([
                    f'{rt}d',
                    '/Gd',
                    '/ZI',
                    '/FS',
                ])
            case BuildType.release:
                flags.extend((rt, '/O2', '/DNDEBUG'))
            case BuildType.release_min_size:
                flags.extend((rt, '/Os', '/DNDEBUG'))
            case  BuildType.release_debug_infos:
                flags.extend((rt, '/O2', '/DNDEBUG'))

        return flags

    @property
    def default_cxxflags(self):
        return [f'/std:c++{self.cpp_std}', *self.settings.cxx_flags]

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

    async def scan_dependencies(self, sourcefile: Path, options: list[str], build_path: Path) -> set[FileDependency]:
        deps_path = build_path / sourcefile.with_suffix(".json").name
        deps = set()
        if deps_path.exists():
            async with aiofiles.open(deps_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
                deps = set(data['Data']['Includes'])
        return deps

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {}

    def debug_files(self, output: Path) -> set[Path]:
        if not self.build_type.is_debug_mode:
            return {}
        return {output.with_suffix('.pdb')}

    @property
    def cxxmodules_flags(self) -> list[str]:
        return list()

    def make_compile_commands(self, sourcefile: Path, output: Path, options: list[str]) -> CommandArgsList:
        deps = output.parent / sourcefile.with_suffix(".json").name
        args = [self.cc, *unique(self.common_flags, self.default_cflags, self.default_cxxflags, options),
                '/sourceDependencies', deps,
                f'/Fo{str(output)}', '/c', str(sourcefile)]
        if self.build_type.is_debug_mode:
            args.append(f'/Fd{str(output.with_suffix(".pdb"))}')
        return [args]

    def make_link_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        return [[self.lnk, *self.common_flags, *options, *objects, f'/OUT:{str(output)}']]

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        objects = list(objects)
        objs = [objects[0].name]
        for obj in objects[1:]:
            objs.append(obj.name)
        return [[self.lib, *self.common_flags, *objs, f'/OUT:{output}']]

    def make_shared_lib_commands(self, objects: set[Path], output: Path, options: list[str]) -> CommandArgsList:
        objects = list(objects)
        objs = [objects[0].name]
        for obj in objects[1:]:
            objs.append(obj.name)
        return [[self.lnk, *self.common_flags,
                f'/IMPLIB:{output.with_suffix(".lib")}', '/DLL', *options, *objs, f'/OUT:{output.with_suffix(".dll")}']]
