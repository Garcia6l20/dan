import os
from pathlib import Path
from typing import Callable
from pymake.core.target import Dependencies, Target, TargetDependencyLike
from pymake.core.utils import AsyncRunner
from pymake.core import asyncio

from . import target_toolchain


class CXXObject(Target):
    def __init__(self, source: str, cxx_flags: set[str] = set()) -> None:
        super().__init__()
        self.source = self.source_path / source
        self.cxx_flags = cxx_flags
        self.toolchain = target_toolchain

    @Target.name.setter
    def name(self, value):
        Target.name.fset(self, f'{value}.{self.source.stem}')

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        if not self.clean_request:
            deps = await self.toolchain.scan_dependencies(self.source, self.cxx_flags)
            deps.add(self.source)
            self.load_dependencies(deps)
        self.output = Path(f'{self.source.name}.o')
        await super().initialize(recursive_once=True)

        self.other_generated_files.update(
            self.toolchain.compile_generated_files(self.output))

    async def __call__(self):
        self.info(f'generating {self.output}...')
        await self.toolchain.compile(self.source, self.output, self.cxx_flags)


class OptionSet:
    def __init__(self, parent: 'CXXTarget',
                 name: str,
                 public: list | set = set(),
                 private: list | set = set(),
                 transform: Callable = None) -> None:
        self._parent = parent
        self._name = name
        self._transform = transform or OptionSet._no_transform
        self._public = set(public)
        self._private = set(private)

    @staticmethod
    def _no_transform(items):
        return items

    @property
    def private(self) -> set:
        return self._transform(self._private)

    @property
    def public(self) -> set:
        items = self._transform(self._public)
        for dep in self._parent.cxx_dependencies:
            items.update(getattr(dep, self._name).public)
        return items

    def add(self, value, public=False):
        if public:
            self._public.add(value)
        else:
            self._private.add(value)

    def update(self, values: 'OptionSet', private=False):
        self._public = values._public
        if private:
            self._private = values._private


class CXXTarget(Target):
    def __init__(self,
                 includes: set[str] = set(),
                 private_includes: set[str] = set(),
                 compile_options: set[str] = set(),
                 private_compile_options: set[str] = set(),
                 compile_definitions: set[str] = set(),
                 private_compile_definitions: set[str] = set(),
                 dependencies: set[TargetDependencyLike] = set(),
                 link_libraries: set[str] = set(),
                 private_link_libraries: set[str] = set(),
                 preload_dependencies: set[TargetDependencyLike] = set()) -> None:
        super().__init__()
        self.toolchain = target_toolchain

        self.dependencies = Dependencies(dependencies)
        self.preload_dependencies = Dependencies(preload_dependencies)
        
        self.includes = OptionSet(self, 'includes',
            transform=self.toolchain.make_include_options)
        
        self.compile_options = OptionSet(self, 'compile_options',
            compile_options, private_compile_options)
        
        self.link_libraries = OptionSet(self, 'link_libraries',
            link_libraries, private_link_libraries, transform=self.toolchain.make_link_options)
        
        self.compile_definitions = OptionSet(self, 'compile_definitions',
            compile_definitions, private_compile_definitions, transform=self.toolchain.make_compile_definitions)

        for path in includes:
            path = Path(path)
            self.includes.add(
                path if path.is_absolute() else self.source_path / path,
                public=True)

        for path in private_includes:
            path = Path(path)
            self.includes.add(
                path if path.is_absolute() else self.source_path / path)


    @property
    def cxx_dependencies(self) -> set['CXXTarget']:
        return {dep for dep in self.dependencies if isinstance(dep, CXXTarget)}

    @property
    def library_dependencies(self) -> set['Library']:
        return {dep for dep in self.dependencies if isinstance(dep, Library)}

    @property
    def libs(self) -> set[str]:
        tmp = self.toolchain.make_link_options(
            {lib.output for lib in self.library_dependencies if lib.output})
        tmp.update(self.link_libraries.public)
        tmp.update(self.link_libraries.private) # TODO move create private_libs()
        for dep in self.cxx_dependencies:
            tmp.update(dep.libs)
        return tmp

    @property
    def cxx_flags(self):
        flags = self.includes.public
        flags.update(self.compile_options.public)
        flags.update(self.compile_definitions.public)
        for dep in self.cxx_dependencies:
            flags.update(dep.cxx_flags)
        return flags

    @property
    def private_cxx_flags(self):
        flags = self.includes.private
        flags.update(self.cxx_flags)
        flags.update(self.compile_options.private)
        flags.update(self.compile_definitions.private)
        return flags

    async def __call__(self):
        # NOP
        return


class CXXObjectsTarget(CXXTarget):
    def __init__(self,
                 sources: set[str] = set(), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.objs: set[CXXObject] = set()

        for source in sources:
            self.objs.add(CXXObject(source, self.private_cxx_flags))

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        for obj in self.objs:
            obj.name = self.name

        self.load_dependencies(self.objs)
        await super().initialize(recursive_once=True)

    async def __call__(self):
        # compile objects
        builds = {dep.build() for dep in self.cxx_dependencies}
        builds.update({dep.build() for dep in self.objs})
        await asyncio.gather(*builds)


class Executable(CXXObjectsTarget, AsyncRunner):

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        self.output = Path(self.sname)
        self.load_dependencies(self.dependencies)
        await super().initialize(recursive_once=True)

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

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        self.load_dependencies(self.objs)
        self.output = Path(f"lib{self.sname}.{self.ext}")
        await super().initialize(recursive_once=True)

    async def __call__(self):
        await super().__call__()
        self.info(
            f'creating {"static" if self.static else "shared"} library {self.output}...')

        objs = self.objs
        for dep in self.cxx_dependencies:
            if isinstance(dep, CXXObjectsTarget):
                objs.update(dep.objs)

        if self.static:
            await self.toolchain.static_lib([str(obj.output) for obj in self.objs], self.output)
        else:
            await self.toolchain.shared_lib([str(obj.output) for obj in self.objs], self.output, {*self.private_cxx_flags, *self.libs})

        self.debug(f'done')


class Module(CXXObjectsTarget):
    def __init__(self, sources: str, *args, **kwargs):
        super().__init__(sources, *args, **kwargs)

    @property
    def cxx_flags(self):
        return {*self.toolchain.cxxmodules_flags, *super().cxx_flags}

    async def __call__(self):
        return await super().__call__()
