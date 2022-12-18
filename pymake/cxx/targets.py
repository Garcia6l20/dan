from collections.abc import Iterable
from enum import Enum
import os
from pymake.core.pathlib import Path
from typing import Callable
from pymake.core import aiofiles, cache
from pymake.core.settings import InstallMode, InstallSettings
from pymake.core.target import Dependencies, Target, TargetDependencyLike
from pymake.core.utils import AsyncRunner, unique
from pymake.core import asyncio


class CXXObject(Target):
    def __init__(self, name, parent: 'CXXTarget', source: str) -> None:
        super().__init__(name, parent=parent, all=False)
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
                deps = [str(d) for d in deps if d.startswith(
                    str(self.source_path)) or d.startswith(str(self.build_path))]
                self.cache.deps = deps
            else:
                deps = self.cache.deps
            self.load_dependencies(deps)
            self.load_dependency(self.source)
        await super().initialize(recursive_once=True)

        self.other_generated_files.update(
            self.toolchain.compile_generated_files(self.output))

        previous_args = self.cache.get('compile_args')
        self.__dirty = False
        if previous_args:
            args = await self.toolchain.compile(self.source, self.output, self.private_cxx_flags, dry_run=True)
            if sorted(args) != sorted(previous_args):
                self.__dirty = True

    @property
    def up_to_date(self):
        if self.__dirty:
            return False
        return super().up_to_date

    async def __call__(self):
        self.info(f'generating {self.output}...')
        self.cache.compile_args = await self.toolchain.compile(self.source, self.output, self.private_cxx_flags)


class OptionSet:
    def __init__(self, parent: 'CXXTarget',
                 name: str,
                 public: list | set = set(),
                 private: list | set = set(),
                 transform: Callable = None) -> None:
        self._parent = parent
        self._name = name
        self._transform = transform or OptionSet._no_transform
        self._public = list(public)
        self._private = list(private)

    @staticmethod
    def _no_transform(items):
        return items

    @property
    def private(self) -> list:
        return unique(self._transform(self._private))

    @property
    def public(self) -> list:
        items: list = self._transform(self._public)
        for dep in self._parent.cxx_dependencies:
            items.extend(getattr(dep, self._name).public)
        return unique(items)

    @property
    def private_raw(self) -> list:
        return self._private

    @property
    def public_raw(self) -> list:
        return self._public

    def add(self, *values, public=False):
        if public:
            for value in values:
                if not value in self._public:
                    self._public.append(value)
        else:
            for value in values:
                if not value in self._private:
                    self._private.append(value)

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
                 **kw_args) -> None:
        super().__init__(name, **kw_args)
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
    def libs(self) -> list[str]:
        tmp = self.toolchain.make_link_options(
            {lib.output for lib in self.library_dependencies if lib.output and not lib.interface})
        tmp.extend(self.link_libraries.public)
        # TODO move create private_libs()
        tmp.extend(self.link_libraries.private)
        for dep in self.cxx_dependencies:
            tmp.extend(dep.libs)
        return unique(tmp)

    @property
    def cxx_flags(self):
        flags = self.includes.public
        flags.extend(self.compile_options.public)
        flags.extend(self.compile_definitions.public)
        for dep in self.cxx_dependencies:
            flags.extend(dep.cxx_flags)
        return unique(flags)

    @property
    def private_cxx_flags(self):
        flags = self.includes.private
        flags.extend(self.cxx_flags)
        flags.extend(self.compile_options.private)
        flags.extend(self.compile_definitions.private)
        return unique(flags)

    async def __call__(self):
        # NOP
        return


class CXXObjectsTarget(CXXTarget):
    def __init__(self, name: str,
                 sources: set[str] | Callable = set(), *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.objs: list[CXXObject] = list()
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
            self.objs.append(
                CXXObject(f'{self.name}.{Path(source).name}', self, source))

    @property
    def file_dependencies(self):
        return unique(super().file_dependencies, *[o.file_dependencies for o in self.objs])

    @property
    def headers(self):
        return [f for f in self.file_dependencies if f.suffix.startswith('.h')]

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

        previous_args = self.cache.get('link_args')
        self.__dirty = False
        if previous_args:
            args = await self.toolchain.link([str(obj.output) for obj in self.objs], self.output, self.libs, dry_run=True)
            if sorted(previous_args) != sorted(args):
                self.__dirty = True

    @property
    def up_to_date(self):
        if self.__dirty:
            return False
        return super().up_to_date

    async def __call__(self):
        await super().__call__()

        # link
        self.info(f'linking {self.output}...')
        self.cache.link_args = await self.toolchain.link([str(obj.output) for obj in self.objs], self.output, self.libs)
        self.debug(f'done')

    @asyncio.once_method
    async def install(self, settings: InstallSettings, mode: InstallMode) -> list[Path]:
        dest = settings.runtime_destination / self.output.name
        if dest.exists() and dest.younger_than(self.output):
            self.info(f'{dest} is up-to-date')
        else:
            self.info(f'installing {dest}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            await aiofiles.copy(self.output, dest)
        return [dest]

    async def execute(self, *args, pipe=False):
        await self.build()
        return await self.run(f'{self.output} {" ".join(args)}', pipe=pipe)


class LibraryType(Enum):
    AUTO = 0
    STATIC = 1
    SHARED = 2
    INTERFACE = 3


class Library(CXXObjectsTarget):

    def __init__(self, *args, library_type: LibraryType = LibraryType.AUTO, **kwargs):
        super().__init__(*args, **kwargs)
        self.library_type = library_type

    @property
    def static(self) -> bool:
        return self.library_type == LibraryType.STATIC

    @property
    def shared(self) -> bool:
        return self.library_type == LibraryType.SHARED

    @property
    def interface(self) -> bool:
        return self.library_type == LibraryType.INTERFACE

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

        if self.library_type == LibraryType.AUTO:
            if len(self.sources) == 0:
                self.library_type = LibraryType.INTERFACE
            else:
                self.library_type = LibraryType.STATIC

        from .msvc_toolchain import MSVCToolchain
        if self.shared and isinstance(self.toolchain, MSVCToolchain):
            self.compile_definitions.add(f'{self.name.upper()}_EXPORT=1')

        if self.library_type != LibraryType.INTERFACE:
            self.load_dependencies(self.objs)
            self.output = self.build_path / f"lib{self.name}.{self.ext}"
        else:
            self.output = self.build_path / f"lib{self.name}.stamp"
        await super().initialize(recursive_once=True)

        previous_args = self.cache.get('generate_args')
        if self.static:
            if previous_args and \
                    previous_args != await self.toolchain.static_lib(
                        [str(obj.output) for obj in self.objs], self.output, self.libs, dry_run=True):
                self.__dirty = True
            else:
                self.__dirty = False
        elif self.shared:
            if previous_args and \
                    previous_args != await self.toolchain.shared_lib(
                        [str(obj.output) for obj in self.objs], self.output, {*self.private_cxx_flags, *self.libs}, dry_run=True):
                self.__dirty = True
            else:
                self.__dirty = False
        else:
            self.__dirty = False

    @property
    def up_to_date(self):
        if self.__dirty:
            return False
        return super().up_to_date

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

    @asyncio.once_method
    async def install(self, settings: InstallSettings, mode: InstallMode) -> list[Path]:
        if mode == InstallMode.user and not self.shared:
            return list()

        tasks = list()

        if settings.create_pkg_config:
            from pymake.pkgconfig.package import create_pkg_config
            tasks.append(create_pkg_config(self, settings))
        
        async def do_install(src: Path, dest: Path):
            if dest.exists() and dest.younger_than(src):
                self.info(f'{dest} is up-to-date')
            else:
                self.info(f'installing {dest}')
                dest.parent.mkdir(parents=True, exist_ok=True)
                await aiofiles.copy(src, dest)
            return dest

        dest = settings.libraries_destination / self.output.name
        tasks.append(do_install(self.output, dest))

        if mode == InstallMode.dev:
            for dependency in self.library_dependencies:
                tasks.append(dependency.install(settings, mode))

            includes_dest = settings.includes_destination
            for public_include_dir in self.includes.public_raw:
                headers = public_include_dir.rglob('*.h*')
                for header in headers:
                    dest = includes_dest / \
                        header.relative_to(public_include_dir)
                    tasks.append(do_install(header, dest))
        return await asyncio.gather(*tasks)


class Module(CXXObjectsTarget):
    def __init__(self, sources: str, *args, **kwargs):
        super().__init__(sources, *args, **kwargs)

    @property
    def cxx_flags(self):
        return {*self.toolchain.cxxmodules_flags, *super().cxx_flags}

    async def __call__(self):
        return await super().__call__()
