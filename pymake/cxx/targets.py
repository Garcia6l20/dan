from collections.abc import Iterable
from enum import Enum
import os
from pymake.core.pathlib import Path
from typing import Callable
from pymake.core import cache
from pymake.core.target import Dependencies, Target, TargetDependencyLike
from pymake.core.utils import AsyncRunner
from pymake.core import asyncio


class CXXObject(Target):
    def __init__(self, name, parent: 'CXXTarget', source: str) -> None:
        super().__init__(name, parent=parent, all=False)
        self.source_path = parent.source_path
        self.build_path = parent.build_path
        self.makefile = parent.makefile
        self.source = self.source_path / source
        from . import target_toolchain
        self.toolchain = target_toolchain

    @property
    def cxx_flags(self):
        return self.parent.cxx_flags

    @property
    def private_cxx_flags(self):
        return self.parent.private_cxx_flags

    @asyncio.once_method
    async def initialize(self):
        await self.parent.preload()
        await self.preload()

        ext = 'o' if os.name != 'nt' else 'obj'
        self.output: Path = self.build_path / \
            Path(f'{self.parent.name}.{self.source.name}.{ext}')

        if not self.clean_request:
            if not self.output.exists() or self.output.stat().st_mtime < self.source.stat().st_mtime or not hasattr(self.cache, 'deps'):
                self.info(f'scanning dependencies of {self.source}')
                deps = await self.toolchain.scan_dependencies(self.source, self.private_cxx_flags, self.build_path)
                deps = [str(d) for d in deps if d.startswith(str(self.source_path)) or d.startswith(str(self.build_path))]
                self.cache.deps = deps
            else:
                deps = self.cache.deps
            self.load_dependencies(deps)
            self.load_dependency(self.source)
        await super().initialize(recursive_once=True)

        self.other_generated_files.update(
            self.toolchain.compile_generated_files(self.output))

    async def __call__(self):
        self.info(f'generating {self.output}...')
        await self.toolchain.compile(self.source, self.output, self.private_cxx_flags)


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

    def add(self, *values, public=False):
        if public:
            for value in values:
                self._public.add(value)
        else:
            for value in values:
                self._private.add(value)

    def update(self, values: 'OptionSet', private=False):
        self._public = values._public
        if private:
            self._private = values._private


class CXXTarget(Target):
    def __init__(self,
                 name: str,
                 includes: set[str] = set(),
                 private_includes: set[str] = set(),
                 compile_options: set[str] = set(),
                 private_compile_options: set[str] = set(),
                 compile_definitions: set[str] = set(),
                 private_compile_definitions: set[str] = set(),
                 dependencies: set[TargetDependencyLike] = set(),
                 link_libraries: set[str] = set(),
                 private_link_libraries: set[str] = set(),
                 preload_dependencies: set[TargetDependencyLike] = set(),
                 all=True) -> None:
        super().__init__(name, all=all)
        from . import target_toolchain
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
            {lib.output for lib in self.library_dependencies if lib.output and not lib.interface})
        tmp.update(self.link_libraries.public)
        # TODO move create private_libs()
        tmp.update(self.link_libraries.private)
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
    def __init__(self, name: str,
                 sources: set[str]|Callable = set(), *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.objs: set[CXXObject] = set()
        self.sources = sources

    @cache.once_method
    def _init_sources(self):
        if callable(self.sources):
            self.sources = set(self.sources())
        if not isinstance(self.sources, Iterable):
            assert callable(
                self.sources), f'{self.name} sources parameter should be an iterable or a callable returning an iterable'
        for source in self.sources:
            source = Path(source)
            if not source.is_absolute():
                source = self.source_path / source
            self.objs.add(
                CXXObject(f'{self.name}.{Path(source).name}', self, source))

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        self._init_sources()

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

        self.output = self.build_path / \
            (self.name if os.name != 'nt' else self.name + '.exe')
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
    class Type(Enum):
        AUTO = 0
        STATIC = 1
        SHARED = 2
        INTERFACE = 3

    def __init__(self, *args, library_type: Type = Type.AUTO, **kwargs):
        super().__init__(*args, **kwargs)
        self.library_type = library_type

    @property
    def static(self) -> bool:
        return self.library_type == self.Type.STATIC

    @property
    def shared(self) -> bool:
        return self.library_type == self.Type.SHARED

    @property
    def interface(self) -> bool:
        return self.library_type == self.Type.INTERFACE

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

        self._init_sources()

        if self.library_type == self.Type.AUTO:
            if len(self.sources) == 0:
                self.library_type = self.Type.INTERFACE
            else:
                self.library_type = self.Type.STATIC

        from .msvc_toolchain import MSVCToolchain
        if self.shared and isinstance(self.toolchain, MSVCToolchain):
            self.compile_definitions.add(f'{self.name.upper()}_EXPORT=1')

        if self.library_type != self.Type.INTERFACE:
            self.load_dependencies(self.objs)
            self.output = self.build_path / f"lib{self.name}.{self.ext}"
        else:
            self.output = self.build_path / f"lib{self.name}.stamp"
        await super().initialize(recursive_once=True)

    async def __call__(self):
        await super().__call__()

        self.info(
            f'creating {self.library_type.name.lower()} library {self.output}...')

        objs = self.objs
        for dep in self.cxx_dependencies:
            if isinstance(dep, CXXObjectsTarget) and not isinstance(dep, Library):
                objs.update(dep.objs)

        if self.static:
            await self.toolchain.static_lib([str(obj.output) for obj in self.objs], self.output, self.libs)
        elif self.shared:
            await self.toolchain.shared_lib([str(obj.output) for obj in self.objs], self.output, {*self.private_cxx_flags, *self.libs})
            from .msvc_toolchain import MSVCToolchain
            if isinstance(self.toolchain, MSVCToolchain):
                self.compile_definitions.add(
                    f'{self.name.upper()}_IMPORT=1', public=True)
        else:
            assert self.interface
            self.output.touch()

        self.debug(f'done')


class Module(CXXObjectsTarget):
    def __init__(self, sources: str, *args, **kwargs):
        super().__init__(sources, *args, **kwargs)

    @property
    def cxx_flags(self):
        return {*self.toolchain.cxxmodules_flags, *super().cxx_flags}

    async def __call__(self):
        return await super().__call__()
