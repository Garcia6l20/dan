from collections.abc import Iterable
from enum import Enum
from functools import cached_property
import os
import re
from pymake.core.pathlib import Path
from typing import Callable
from pymake.core import aiofiles, cache
from pymake.core.settings import InstallMode, InstallSettings
from pymake.core.target import Dependencies, Target, TargetDependencyLike
from pymake.core.utils import unique
from pymake.core.runners import async_run
from pymake.core import asyncio


class CXXObject(Target):
    def __init__(self, name, parent: 'CXXTarget', source: str) -> None:
        super().__init__(name, parent=parent, all=False)
        self.source = self.source_path / source
        from . import target_toolchain
        self.toolchain = target_toolchain
        self.__dirty = False

    @property
    def cxx_flags(self):
        return self.parent.cxx_flags

    @property
    def private_cxx_flags(self):
        return self.parent.private_cxx_flags

    async def __initialize__(self):
        await self.parent.preload()

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

        self.other_generated_files.update(
            self.toolchain.compile_generated_files(self.output))

        previous_args = self.cache.get('compile_args')
        if previous_args:
            args = self.toolchain.make_compile_commands(
                self.source, self.output, self.private_cxx_flags)[0]
            args = [str(arg) for arg in args]
            if sorted(args) != sorted(previous_args):
                self.__dirty = True
        else:
            self.__dirty = True

    @property
    def up_to_date(self):
        res = super().up_to_date
        if res and self.__dirty:
            res = False
        return res

    async def __build__(self):
        self.info(f'generating {self.output}...')
        commands = await self.toolchain.compile(self.source, self.output, self.private_cxx_flags)
        self.cache.compile_args = [str(a) for a in commands[0]]


class OptionSet:
    def __init__(self, parent: 'CXXTarget',
                 name: str,
                 public: list | set = set(),
                 private: list | set = set(),
                 transform: Callable = None) -> None:
        self._parent = parent
        self._name = name
        self._transform = transform or (lambda x: x)
        self._public = list(public)
        self._private = list(private)

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
                 link_options: set[str] = set(),
                 private_link_options: set[str] = set(),
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

        self.link_options = OptionSet(self, 'link_options',
                                      link_options, private_link_options)

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
        tmp = list()
        tmp.extend(self.link_libraries.public)
        # TODO move create private_libs()
        tmp.extend(self.link_libraries.private)
        for dep in self.cxx_dependencies:
            tmp.extend(dep.libs)
        return unique(tmp)

    @cached_property
    def cxx_flags(self):
        flags = self.includes.public
        flags.extend(self.compile_options.public)
        flags.extend(self.compile_definitions.public)
        for dep in self.cxx_dependencies:
            flags.extend(dep.cxx_flags)
        return unique(flags)

    @cached_property
    def private_cxx_flags(self):
        flags = self.includes.private
        flags.extend(self.cxx_flags)
        flags.extend(self.compile_options.private)
        flags.extend(self.compile_definitions.private)
        return unique(flags)


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

    async def __initialize__(self):
        self._init_sources()
        async with asyncio.TaskGroup() as group:
            for obj in self.objs:
                group.create_task(obj.initialize())
                self.load_dependency(obj)

    async def __build__(self):
        # compile objects
        async with asyncio.TaskGroup() as group:
            for dep in self.objs:
                group.create_task(dep.build())


class Executable(CXXObjectsTarget):

    def __init__(self, name: str, sources: set[str] | Callable = set(), *args, **kwargs):
        super().__init__(name, sources, *args, **kwargs)

        self.output = self.build_path / \
            self.toolchain.make_executable_name(self.name)
        self.__dirty = False

    async def __initialize__(self):
        await super().__initialize__()

        previous_args = self.cache.get('link_args')
        if previous_args:
            args = self.toolchain.make_link_commands([str(obj.output) for obj in self.objs], self.output,
                                                     [*self.libs, *self.link_options.public, *self.link_options.private])[0]
            args = [str(a) for a in args]
            if sorted(previous_args) != sorted(args):
                self.__dirty = True

    @property
    def up_to_date(self):
        if self.__dirty:
            return False
        return super().up_to_date

    async def __build__(self):
        await super().__build__()

        # link
        self.info(f'linking {self.output}...')
        commands = await self.toolchain.link([str(obj.output) for obj in self.objs], self.output,
                                             [*self.libs, *self.link_options.public, *self.link_options.private])
        self.cache.link_args = [str(a) for a in commands[0]]
        self.debug(f'done')

    @asyncio.cached
    async def install(self, settings: InstallSettings, mode: InstallMode) -> list[Path]:
        dest = settings.runtime_destination / self.output.name
        if dest.exists() and dest.younger_than(self.output):
            self.info(f'{dest} is up-to-date')
        else:
            self.info(f'installing {dest}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            await aiofiles.copy(self.output, dest)
        return [dest]

    async def execute(self, *args, **kwargs):
        await self.build()
        return await async_run([self.output, *args], logger=self, env=self.toolchain.env, **kwargs)


class LibraryType(Enum):
    AUTO = 0
    STATIC = 1
    SHARED = 2
    INTERFACE = 3


class Library(CXXObjectsTarget):

    def __init__(self, *args, library_type: LibraryType = LibraryType.AUTO, **kwargs):
        super().__init__(*args, **kwargs)
        self.library_type = library_type
        self.header_match = r'.+'

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
    def libs(self) -> list[str]:
        tmp = super().libs
        if not self.interface:
            tmp.extend(self.toolchain.make_link_options([self.output]))
        return tmp

    async def __initialize__(self):
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
            self.output = self.build_path / \
                self.toolchain.make_library_name(self.name, self.shared)
        else:
            self.output = self.build_path / f"lib{self.name}.stamp"
        await super().__initialize__()

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

    async def __build__(self):
        await super().__build__()

        self.info(
            f'creating {self.library_type.name.lower()} library {self.output}...')

        objs = self.objs
        for dep in self.cxx_dependencies:
            if isinstance(dep, CXXObjectsTarget) and not isinstance(dep, Library):
                objs.update(dep.objs)

        if self.static:
            await self.toolchain.static_lib([obj.output for obj in self.objs], self.output, self.libs)
        elif self.shared:
            await self.toolchain.shared_lib([obj.output for obj in self.objs], self.output, {*self.private_cxx_flags, *self.libs})
            from .msvc_toolchain import MSVCToolchain
            if isinstance(self.toolchain, MSVCToolchain):
                self.compile_definitions.add(
                    f'{self.name.upper()}_IMPORT=1', public=True)
        else:
            assert self.interface
            self.output.touch()

        self.debug(f'done')

    @asyncio.cached
    async def install(self, settings: InstallSettings, mode: InstallMode) -> list[Path]:
        if mode == InstallMode.user and not self.shared:
            return list()

        await self.build()

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
        if not self.interface:
            tasks.append(do_install(self.output, dest))

        if mode == InstallMode.dev:
            for dependency in self.library_dependencies:
                tasks.append(dependency.install(settings, mode))

            header_expr = re.compile(self.header_match)
            includes_dest = settings.includes_destination
            for public_include_dir in self.includes.public_raw:
                headers = public_include_dir.rglob('*.h*')
                for header in headers:
                    if header_expr.match(str(header)):
                        dest = includes_dest / \
                            header.relative_to(public_include_dir)
                        tasks.append(do_install(header, dest))
        return await asyncio.gather(super().install(settings, mode), *tasks)


class Module(CXXObjectsTarget):
    def __init__(self, sources: str, *args, **kwargs):
        super().__init__(sources, *args, **kwargs)

    @property
    def cxx_flags(self):
        return {*self.toolchain.cxxmodules_flags, *super().cxx_flags}

    async def __build__(self):
        return await super().__build__()
