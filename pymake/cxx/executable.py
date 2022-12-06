import asyncio
from pathlib import Path
import sys
from pymake.core.target import Target
from pymake.core.utils import AsyncRunner

from .toolchain import Toolchain
from .gcc_toolchain import GCCToolchain

_target_toolchain: Toolchain = None


def target_toolchain() -> Toolchain:
    global _target_toolchain
    if _target_toolchain is None:
        _target_toolchain = GCCToolchain()
    return _target_toolchain


class CXXObject(Target):
    def __init__(self, source: str, include_opts: list[str]) -> None:
        super().__init__()
        self.source = self.source_path / source
        self.include_opts = include_opts
        self.toolchain = target_toolchain()

    async def __initialize__(self, name: str):
        deps = await self.toolchain.scan_dependencies(self.source, self.include_opts)
        deps.insert(0, self.source)
        base_name = self.source.stem
        await super().__initialize__(f'{name}.{base_name}', f'{base_name}.o', deps)

    async def __call__(self):
        self.info(f'generating {self.output}...')
        await self.toolchain.compile(self.source, self.output, self.include_opts)


class Executable(Target, AsyncRunner):
    def __init__(self, sources: str, include_paths: list[str]):
        super().__init__()
        self.toolchain = target_toolchain()
        self.objs: list[CXXObject] = list()
        self.include_paths: list[Path] = list()
        for path in include_paths:
            path = Path(path)
            self.include_paths.append(
                path if path.is_absolute() else self.source_path / path)
        self.include_opts = self.toolchain.make_include_options(
            self.include_paths)
        for source in sources:
            self.objs.append(CXXObject(source, self.include_opts))

    async def __initialize__(self, name: str):
        await asyncio.gather(*[obj.__initialize__(name) for obj in self.objs])
        await super().__initialize__(name, name.split('.')[-1], self.objs)

    async def __call__(self):
        # compile objects
        await asyncio.gather(*[obj.build() for obj in self.objs])
        # link them
        objs = [str(obj.output) for obj in self.objs]
        self.info(f'linking {self.output}...')
        await self.toolchain.link(objs, self.output, self.include_opts)

    async def execute(self, *args):
        await self.build()
        out, err = await self.run(f'{self.output} {" ".join(args)}', pipe=False)
