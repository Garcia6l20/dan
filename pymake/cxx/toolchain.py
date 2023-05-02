from enum import Enum
from pymake.core.asyncio import sync_wait
from pymake.core.pathlib import Path
from pymake.core.settings import BuildType
from pymake.core.target import FileDependency
from pymake.core.runners import async_run, sync_run, CommandError
from pymake.core.version import Version
from pymake.logging import Logging
from pymake.cxx.compile_commands import CompileCommands

import tempfile


scan = True

CommandArgs = list[str|Path]
CommandArgsList = list[CommandArgs]

class RuntimeType(Enum):
    static = 0
    dynamic = 1

class Toolchain(Logging):
    def __init__(self, data) -> None:
        self.cc : Path = None
        self.cxx : Path = None
        self._compile_commands: CompileCommands = None
        self.cxx_flags = set()
        self.cpp_std = 17
        self.type = data['type']
        self.arch = data['arch']
        self.system = data['system']
        self.version = Version(data['version'])
        Logging.__init__(self, f'{self.type}-{self.version}')
        self.env = None
        self.rpath = None
        self._build_type = BuildType.debug
        self.compile_options: list[str] = list()
        self.link_options: list[str] = list()
        self.rpath = None
        self.runtime = RuntimeType.dynamic

    @property
    def build_type(self):
        return self._build_type
    
    @property
    def compile_commands(self):
        if not self._compile_commands:
            self._compile_commands = CompileCommands()
        return self._compile_commands

    def init(self, mode: str):
        raise NotImplementedError()

    def has_cxx_compile_options(*opts) -> bool:
        raise NotImplementedError()

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        raise NotImplementedError()

    def make_include_options(self, include_paths: set[Path]) -> list[str]:
        raise NotImplementedError()

    def make_link_options(self, libraries: set[Path]) -> list[str]:
        raise NotImplementedError()

    def make_library_name(self, basename: str, shared: bool) -> str:
        raise NotImplementedError()

    def make_executable_name(self, basename: str) -> str:
        raise NotImplementedError()
    
    async def scan_dependencies(self, file: Path, options: set[str], build_path: Path) -> set[FileDependency]:
        raise NotImplementedError()

    def compile_generated_files(self, output: Path) -> set[Path]:
        return set()

    def make_compile_commands(self, sourcefile: Path, output: Path, options: set[str]) -> CommandArgsList:
        raise NotImplementedError()
    
    def from_unix_flags(self, flags: list[str]) -> list[str]:
        """Convert flags from unix-style to target-compiler-style"""
        return flags
    
    def to_unix_flags(self, flags: list[str]) -> list[str]:
        """Convert flags from target-compiler-style to unix-style"""
        return flags

    async def compile(self, sourcefile: Path, output: Path, options: set[str], **kwds):
        commands = self.make_compile_commands(sourcefile, output, options)
        self.compile_commands.insert(sourcefile, output.parent, commands[0])
        for index, command in enumerate(commands):
            await self.run(f'compile{index}', output, command, **kwds, cwd=output.parent)
        return commands

    def make_link_commands(self, objects: set[Path], output: Path, options: set[str]) -> CommandArgsList:
        raise NotImplementedError()

    async def link(self, objects: set[Path], output: Path, options: set[str], **kwds):
        commands = self.make_link_commands(objects, output, options)
        for index, command in enumerate(commands):
            await self.run(f'link{index}', output, command, **kwds, cwd=output.parent)
        return commands

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: set[str]) -> CommandArgsList:
        raise NotImplementedError()

    async def static_lib(self, objects: set[Path], output: Path, options: set[str], **kwds):
        commands = self.make_static_lib_commands(objects, output, options)
        for index, command in enumerate(commands):
            await self.run(f'static_lib{index}', output, command, **kwds, cwd=output.parent)
        return commands

    def make_static_lib_commands(self, objects: set[Path], output: Path, options: set[str]) -> CommandArgsList:
        raise NotImplementedError()

    async def shared_lib(self, objects: set[Path], output: Path, options: set[str], **kwds):
        commands = self.make_static_lib_commands(objects, output, options)
        for index, command in enumerate(commands):
            await self.run(f'shared_lib{index}', output, command, **kwds, cwd=output.parent)
        return commands

    async def run(self, name: str, output: Path, args, quiet=False, **kwds):
        return await async_run(args, env=self.env, logger=self if not quiet else None, **kwds)

    @property
    def cxxmodules_flags(self) -> list[str]:
        ...

    def can_compile(self, source: str, options: set[str] = set(), extension='.cpp'):
        with tempfile.NamedTemporaryFile('w', suffix=extension) as f:
            f.write(source)
            f.flush()
            try:
                fname = Path(f.name)
                sync_run(self.make_compile_commands(fname, fname.with_suffix('.o'), options)[0])
                return True
            except CommandError as err:
                print(err)
                return False

    def has_include(self, *includes, options: set[str] = set(), extension='.cpp'):
        source = '\n'.join([f'#include {inc}' for inc in includes])
        return self.can_compile(source, options, extension)

    def has_definition(self, *definitions, options: set[str] = set(), extension='.cpp'):
        source = '\n'.join([f'''#ifndef {d}
        #error "{d} is not defined"
        #endif''' for d in definitions])
        return self.can_compile(source, options, extension)
