from pymake.core.pathlib import Path
from pymake.core.settings import BuildType
from pymake.core.target import FileDependency
from pymake.core.utils import AsyncRunner
from pymake.core.version import Version
from pymake.logging import Logging
from pymake.cxx.compile_commands import CompileCommands


scan = True


class Toolchain(AsyncRunner, Logging):
    def __init__(self, data) -> None:
        self._compile_commands: CompileCommands = None
        self.cxx_flags = set()
        self.cpp_std = 17
        self.type = data['type']
        self.version = Version(data['version'])
        Logging.__init__(self, f'{self.type}-{self.version}')
        self.env = None
        self.rpath = None
        self._build_type = BuildType.debug
        self.compile_options : list[str] = list()
        self.link_options : list[str] = list()

    @property
    def build_type(self):
        return self._build_type

    @property
    def compile_commands(self):
        if not self._compile_commands:
            self._compile_commands = CompileCommands()
        return self._compile_commands

    def init(self, mode: str):
        ...

    def has_cxx_compile_options(*opts) -> bool:
        ...

    def make_compile_definitions(self, definitions: set[str]) -> list[str]:
        ...

    def make_include_options(self, include_paths: set[Path]) -> list[str]:
        ...

    def make_link_options(self, libraries: set[Path]) -> list[str]:
        ...

    async def scan_dependencies(self, file: Path, options: set[str], build_path: Path) -> set[FileDependency]:
        ...

    def compile_generated_files(self, output: Path) -> set[Path]:
        return set()

    async def compile(self, sourcefile: Path, output: Path, options: set[str], dry_run=False):
        ...

    async def link(self, objects: set[Path], output: Path, options: set[str], dry_run=False):
        ...

    async def static_lib(self, objects: set[Path], output: Path, options: set[str], dry_run=False):
        ...

    async def shared_lib(self, objects: set[Path], output: Path, options: set[str], dry_run=False):
        ...

    async def run(self, name: str, output: Path, args, **kwargs):
        return await super().run(args, env=self.env, **kwargs)

    @property
    def cxxmodules_flags(self) -> list[str]:
        ...
