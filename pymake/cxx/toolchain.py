from pathlib import Path

from pymake.core.target import FileDependency
from pymake.core.include import root_makefile
import json

scan = True


class CompileCommands:
    def __init__(self) -> None:
        self.cc_path: Path = root_makefile.build_path / 'compile_commands.json'
        if self.cc_path.exists():
            self.cc_f = open(self.cc_path, 'r+')
            try:
                self.data = json.load(self.cc_f)
            except json.JSONDecodeError:
                self.data = list()
        else:
            self.data = list()
            self.cc_path.parent.mkdir(parents=True, exist_ok=True)
            self.cc_f = open(self.cc_path, 'w')

    def clear(self):
        self.cc_f.seek(0)
        self.cc_f.truncate()
        self.cc_f.close()

    def update(self):
        self.cc_f.seek(0)
        self.cc_f.truncate()
        json.dump(self.data, self.cc_f)
        self.cc_f.close()

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
            key = 'args'
        if entry:
            entry[key] = content
        else:
            self.data.append({
                'file': str(file),
                'directory': str(build_path),
                key: content
            })


class Toolchain:
    def __init__(self) -> None:
        self.compile_commands = CompileCommands()
        self.cxx_flags = set()

    def has_cxx_compile_options(*opts) -> bool:
        ...

    def make_compile_definitions(self, definitions: set[str]) -> set[str]:
        ...

    def make_include_options(self, include_paths: set[Path]) -> set[str]:
        ...

    def make_link_options(self, libraries: set[Path]) -> set[str]:
        ...

    async def scan_dependencies(self, file: Path, options: set[str]) -> set[FileDependency]:
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

    @property
    def cxxmodules_flags(self) -> set[str]:
        ...
