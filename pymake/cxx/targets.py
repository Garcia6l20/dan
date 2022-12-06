import asyncio
import os
from pathlib import Path
import sys
from pymake.core.target import Target, TargetDependencyLike
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
        await super().__initialize__(f'{name}.{self.source.stem}', f'{self.source.name}.o', deps)
        
        self.other_generated_files.extend(self.toolchain.compile_generated_files(self.output))

    async def __call__(self):
        self.info(f'generating {self.output}...')
        await self.toolchain.compile(self.source, self.output, self.include_opts)


class CXXTarget(Target):
    def __init__(self, sources: str, public_includes: list[str] = list(), private_includes: list[str] = list(), dependencies: list[TargetDependencyLike] = list()):
        super().__init__()
        self.toolchain = target_toolchain()
        self.objs: list[CXXObject] = list()
        self.dependencies = dependencies if isinstance(dependencies, list) else [dependencies]
        self.public_includes: list[Path] = list()
        self.private_includes: list[Path] = list()

        for path in public_includes:
            path = Path(path)
            self.public_includes.append(
                path if path.is_absolute() else self.source_path / path)

        for dep in [dep for dep in self.dependencies if isinstance(dep, CXXTarget)]:
            self.public_includes.extend(dep.public_includes)

        for path in private_includes:
            path = Path(path)
            self.private_includes.append(
                path if path.is_absolute() else self.source_path / path)

        self.include_opts = self.toolchain.make_include_options(
            [*self.public_includes, *self.private_includes])

        for source in sources:
            self.objs.append(CXXObject(source, self.include_opts))

    @property
    def cxx_dependencies(self) -> list['CXXTarget']:
        return [dep for dep in self.dependencies if isinstance(dep, CXXTarget)]

    @property
    def library_dependencies(self) -> list['Library']:
        return [dep for dep in self.dependencies if isinstance(dep, Library)]

    @property
    def link_opts(self) -> list[str]:        
        return self.toolchain.make_link_options([lib.output for lib in self.library_dependencies])

    @property
    def all_options(self):
        return [*self.link_opts, *self.include_opts]

    async def __call__(self):
        # compile objects
        await asyncio.gather(*[dep.build() for dep in self.library_dependencies], *[obj.build() for obj in self.objs])

    async def execute(self, *args):
        await self.build()
        await self.run(f'{self.output} {" ".join(args)}', pipe=False)


class Executable(CXXTarget, AsyncRunner):

    async def __initialize__(self, name: str):
        await asyncio.gather(*[obj.__initialize__(name) for obj in self.objs])
        await super().__initialize__(name, name.split('.')[-1], [*self.dependencies, *self.objs])

    async def __call__(self):
        await super().__call__()

        # link
        self.info(f'linking {self.output}...')
        await self.toolchain.link([str(obj.output) for obj in self.objs], self.output, self.all_options)
        self.debug(f'done')


class Library(CXXTarget, AsyncRunner):
    def __init__(self, *args, static=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.static = static

    @property
    def ext(self):
        if os.name == 'posix':
            return 'a' if self.static else 'so'
        elif os.name == 'nt':
            return 'lib' if self.static else 'dll'
        else:
            raise RuntimeError(f'Unknwon os name: {os.name}')

    async def __initialize__(self, name: str):
        await asyncio.gather(*[obj.__initialize__(name) for obj in self.objs])
        await super().__initialize__(name, f"lib{name.split('.')[-1]}.{self.ext}", self.objs)

    async def __call__(self):
        await super().__call__()
        self.info(f'creating {"static" if self.static else "shared"} library {self.output}...')

        if self.static:
            await self.toolchain.static_lib([str(obj.output) for obj in self.objs], self.output)
        else:
            await self.toolchain.shared_lib([str(obj.output) for obj in self.objs], self.output, self.all_options)

        self.debug(f'done')
