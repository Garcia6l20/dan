import asyncio
from pymake.core.pathlib import Path

import aiofiles

from pymake.core.target import FileDependency
import json

from pymake.core.utils import AsyncRunner
from pymake.logging import Logging

scan = True


class CompileCommands:
    def __init__(self) -> None:
        from pymake.core.include import context
        self.cc_path: Path = context.root.build_path / 'compile_commands.json'
        if self.cc_path.exists():
            with open(self.cc_path, 'r') as cc_f:
                try:
                    self.data = json.load(cc_f)
                except json.JSONDecodeError:
                    self.data = list()
        else:
            self.data = list()
            self.cc_path.parent.mkdir(parents=True, exist_ok=True)

    def clear(self):
        with open(self.cc_path, 'w'):
            pass

    def update(self):
        with open(self.cc_path, 'w') as cc_f:
            json.dump(self.data, cc_f)

    def get(self, file: Path):
        fname = file.name
        for entry in self.data:
            if entry['file'] == fname:
                return entry
        return None

    def insert(self, file: Path, build_path: Path, content: list[str] | str):
        entry = self.get(file)
        if isinstance(content, str):
            key = 'command'
        else:
            assert isinstance(content, list)
            content = [str(item) for item in content]
            key = 'args'
        if entry:
            entry[key] = content
        else:
            self.data.append({
                'file': str(file),
                'directory': str(build_path),
                key: content
            })


class Toolchain(AsyncRunner, Logging):
    def __init__(self) -> None:
        self._compile_commands: CompileCommands = None
        self.cxx_flags = set()
        self.cpp_std = 17
        self.env = None
    
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

    async def compile(self, sourcefile: Path, output: Path, options: set[str]):
        ...

    async def link(self, objects: set[Path], output: Path, options: set[str]):
        ...

    async def static_lib(self, objects: set[Path], output: Path, options: set[str]):
        ...

    async def shared_lib(self, objects: set[Path], output: Path, options: set[str]):
        ...

    async def run(self, name: str, output: Path, args, **kwargs):
        return await super().run(args, env=self.env, **kwargs)

    @property
    def cxxmodules_flags(self) -> list[str]:
        ...
