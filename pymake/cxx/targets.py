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
    def __init__(self, source: str, cxxflags: set[str] = set()) -> None:
        super().__init__()
        self.source = self.source_path / source
        self.cxxflags = cxxflags
        self.toolchain = target_toolchain()

    async def __initialize__(self, name: str):
        deps = await self.toolchain.scan_dependencies(self.source, self.cxxflags)
        deps.add(self.source)
        await super().__initialize__(f'{name}.{self.source.stem}', f'{self.source.name}.o', deps)

        self.other_generated_files.update(
            self.toolchain.compile_generated_files(self.output))

    async def __call__(self):
        self.info(f'generating {self.output}...')
        await self.toolchain.compile(self.source, self.output, self.cxxflags)


class CXXTarget(Target):
    def __init__(self,
                 public_includes: set[str] = set(),
                 private_includes: set[str] = set(),
                 public_compile_options: set[str] = set(),
                 private_compile_options: set[str] = set(),
                 dependencies: set[TargetDependencyLike] = set()) -> None:
        super().__init__()
        self.toolchain = target_toolchain()

        self.dependencies = set(dependencies)
        self.public_includes: set[Path] = set()
        self.private_includes: set[Path] = set()
        self.public_compile_options = set(public_compile_options)
        self.private_compile_options = set(private_compile_options)

        for path in public_includes:
            path = Path(path)
            self.public_includes.add(
                path if path.is_absolute() else self.source_path / path)

        for dep in [dep for dep in self.dependencies if isinstance(dep, CXXTarget)]:
            self.public_includes.update(dep.public_includes)

        for path in private_includes:
            path = Path(path)
            self.private_includes.add(
                path if path.is_absolute() else self.source_path / path)

        self.include_opts = self.toolchain.make_include_options(
            [*self.public_includes, *self.private_includes])

    @property
    def cxx_dependencies(self) -> set['CXXTarget']:
        return {dep for dep in self.dependencies if isinstance(dep, CXXTarget)}

    @property
    def library_dependencies(self) -> set['Library']:
        return {dep for dep in self.dependencies if isinstance(dep, Library)}

    @property
    def libs(self) -> set[str]:
        tmp = self.toolchain.make_link_options([lib.output for lib in self.library_dependencies if lib.output])
        for dep in self.cxx_dependencies:
            tmp.update(dep.libs)
        return tmp

    @property
    def cxxflags(self):
        flags = self.include_opts
        flags.update(self.public_compile_options)
        flags.update(self.private_compile_options)
        for dep in self.cxx_dependencies:
            flags.update(dep.cxxflags)
        return flags

    async def __call__(self):
        # NOP
        return


class CXXObjectsTarget(CXXTarget):
    def __init__(self,
                 sources: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.objs: set[CXXObject] = set()

        for source in sources:
            self.objs.add(CXXObject(source, self.cxxflags))

    async def __call__(self):
        # compile objects
        await asyncio.gather(*[dep.build() for dep in self.library_dependencies], *[obj.build() for obj in self.objs])


class Executable(CXXObjectsTarget, AsyncRunner):

    async def __initialize__(self, name: str):
        await asyncio.gather(*[obj.__initialize__(name) for obj in self.objs])
        await super().__initialize__(name, name.split('.')[-1], {*self.dependencies, *self.objs})

    async def __call__(self):
        await super().__call__()

        # link
        self.info(f'linking {self.output}...')
        await self.toolchain.link([str(obj.output) for obj in self.objs], self.output, self.libs)
        self.debug(f'done')

    async def execute(self, *args):
        await self.build()
        await self.run(f'{self.output} {" ".join(args)}', pipe=False)


class Library(CXXObjectsTarget):
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
        self.info(
            f'creating {"static" if self.static else "shared"} library {self.output}...')

        if self.static:
            await self.toolchain.static_lib([str(obj.output) for obj in self.objs], self.output)
        else:
            await self.toolchain.shared_lib([str(obj.output) for obj in self.objs], self.output, {*self.cxxflags, *self.libs})

        self.debug(f'done')

class Module(CXXObjectsTarget):
    def __init__(self, sources: str, *args, **kwargs):
        super().__init__(sources, *args, **kwargs)

    @property
    def cxxflags(self):
        return {*self.toolchain.cxxmodules_flags, *super().cxxflags}

    async def __call__(self):
        return await super().__call__()
