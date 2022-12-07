from pathlib import Path

from pymake.core.target import FileDependency


class Toolchain:
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
