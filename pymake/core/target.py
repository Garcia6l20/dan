from functools import cached_property
from pathlib import Path
from typing import Union, TypeAlias
import inspect

from pymake.core import asyncio, aiofiles, utils
from pymake.core.cache import SubCache
from pymake.logging import Logging


class Dependencies(set):
    def __getattr__(self, attr):
        for item in self:
            if item.name == attr:
                return item

    @property
    def up_to_date(self):
        for item in self:
            if not item.up_to_date:
                return False
        return True

    @property
    def modification_time(self):
        t = 0.0
        for item in self:
            mt = item.modification_time
            if mt and mt > t:
                t = mt
        return t

TargetDependencyLike: TypeAlias = Union[list['Target'], 'Target']


PathImpl = type(Path())


class FileDependency(PathImpl):
    def __init__(self, *args, **kwargs):
        super(PathImpl, self).__init__()
        self.up_to_date = True

    @property
    def modification_time(self):
        return self.stat().st_mtime


class Target(Logging):
    clean_request = False

    def __init__(self, name: str = None, parent:'Target' = None) -> None:
        from pymake.core.include import current_makefile
        self.source_path = current_makefile.source_path
        self.build_path = current_makefile.build_path
        self.other_generated_files: set[Path] = set()
        self.dependencies: Dependencies[Target] = Dependencies()
        self.preload_dependencies: Dependencies[Target] = Dependencies()
        self._name: str = None        
        self.output: Path = None
        self.parent = parent
        
        if name:
            if current_makefile.parent:
                self.name = f'{current_makefile.parent.name}.{name}'
            else:
                self.name = name

    @property
    def name(self) -> str:
        return self._name

    @cached_property
    def sname(self) -> str:
        return self._name.split('.')[-1]

    @cached_property
    def cache(self) -> SubCache:
        from pymake.core.globals import cache
        return cache.subcache(self._name)

    @name.setter
    def name(self, name):
        if self._name:
            return
        self._name = name
        super().__init__(self.name)

    @asyncio.once_method
    async def preload(self):
        await asyncio.gather(*[obj.preload() for obj in self.target_dependencies])
        await asyncio.gather(*[obj.initialize() for obj in self.preload_dependencies])

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        await asyncio.gather(*[obj.initialize() for obj in self.target_dependencies])
        if self.output and not self.output.is_absolute():
            self.output = self.build_path / self.output

    def load_dependencies(self, dependencies):
        for dependency in dependencies:
            self.load_dependency(dependency)

    def load_dependency(self, dependency):
        if isinstance(dependency, Target):
            self.dependencies.add(dependency)
        elif isinstance(dependency, FileDependency):
            self.dependencies.add(dependency)
        elif isinstance(dependency, str):
            self.load_dependency(Path(dependency))
        elif isinstance(dependency, Path):
            dependency = FileDependency(self.source_path / dependency)
            self.dependencies.add(dependency)
        else:
            raise RuntimeError(
                f'Unhandled dependency {dependency} ({type(dependency)})')

    @property
    def modification_time(self):
        return self.output.stat().st_mtime if self.output else None

    @property
    def up_to_date(self):
        if self.output and not self.output.exists():
            return False
        if not self.dependencies.up_to_date:
            return False
        if self.modification_time and self.dependencies.modification_time > self.modification_time:
            return False
        return True

    @asyncio.once_method
    async def build(self):
        await self.initialize()

        if self.up_to_date:
            self.info('up to date !')
            return

        with utils.chdir(self.build_path):
            self.info('building...')
            result = self()
            if inspect.iscoroutine(result):
                return await result
            return result

    @property
    def target_dependencies(self):
        return [t for t in self.dependencies if isinstance(t, Target)]

    @asyncio.once_method
    async def clean(self):
        await self.initialize()

        clean_tasks = [t.clean() for t in self.target_dependencies]
        if self.output and self.output.exists():
            self.info('cleaning...')
            if self.output.is_dir():
                clean_tasks.append(aiofiles.rmtree(self.output))
            else:
                clean_tasks.append(aiofiles.os.remove(self.output))
        clean_tasks.extend([aiofiles.os.remove(f)
                           for f in self.other_generated_files if f.exists()])
        try:
            await asyncio.gather(*clean_tasks)
        except FileNotFoundError as err:
            self.warn(f'file not found: {err.filename}')

    def __call__(self):
        ...
