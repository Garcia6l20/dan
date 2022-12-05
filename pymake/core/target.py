from pathlib import Path
from typing import Callable, Union, TypeAlias
import inspect
import asyncio
import aiofiles
import aiofiles.os

from pymake.core.logging import Logging


class Dependencies(list):
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
            if mt > t:
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
    def __new__(cls, *args, **kwargs):
        self = super().__new__(cls)
        stack_trace = inspect.stack()
        stack_trace = inspect.stack()
        for frame in stack_trace:
            if frame.filename.endswith('makefile.py') and frame.function == '<module>':
                self.source_path = Path(frame.filename).parent
        return self

    async def __initialize__(self, name: str, output: str, dependencies: TargetDependencyLike = None):
        self.name = name
        super().__init__(self.name)
        self.output = Path(output)
        self.dependencies: Dependencies[Target] = Dependencies()
        if isinstance(dependencies, list):
            self.load_dependencies(dependencies)
        elif dependencies is not None:
            self.load_dependency(dependencies)

    def load_dependencies(self, dependencies):
        for dependency in dependencies:
            self.load_dependency(dependency)

    def load_dependency(self, dependency):
        if isinstance(dependency, Target):
            self.dependencies.append(dependency)
        elif isinstance(dependency, FileDependency):
            self.dependencies.append(dependency)
        elif isinstance(dependency, str):
            self.load_dependency(Path(dependency))
        elif isinstance(dependency, Path):
            dependency = FileDependency(self.source_path / dependency)
            if not dependency.exists():
                raise FileNotFoundError(dependency)
            self.dependencies.append(dependency)
        else:
            raise RuntimeError(
                f'Unhandled dependency {dependency} ({type(dependency)})')

    @property
    def modification_time(self):
        return self.output.stat().st_mtime

    @property
    def up_to_date(self):
        if not self.output.exists():
            return False
        if not self.dependencies.up_to_date:
            return False
        if self.dependencies.modification_time > self.modification_time:
            return False
        return True

    async def build(self):
        if self.up_to_date:
            self.debug('not building, up to date !')
            return
        self.debug('building...')
        result = self()
        if inspect.iscoroutine(result):
            return await result
        return result

    @property
    def target_dependencies(self):
        return [t for t in self.dependencies if isinstance(t, Target)]

    async def clean(self):
        self.debug('cleaning...')
        clean_tasks = [t.clean() for t in self.target_dependencies]
        if self.output.exists():
            clean_tasks.append(aiofiles.os.remove(self.output))
        await asyncio.gather(*clean_tasks)

    def __call__(self):
        ...


class target:
    def __init__(self, output: str, dependencies: TargetDependencyLike = None, name=None):
        self.output = output
        self.dependencies = dependencies

    def __call__(self, fn: Callable):
        class TargetImpl(Target):
            def __init__(self, output, dependencies) -> None:
                super().__init__()
                self.output = output
                self.dependencies = dependencies

            async def __initialize__(self, name):
                await super().__initialize__(name, self.output, self.dependencies)

            def __call__(self):
                arg_spec = inspect.getfullargspec(fn)
                args = list()
                kwargs = dict()
                if 'self' in arg_spec.args:
                    args.append(self)
                return fn(*args, **kwargs)
        return TargetImpl(self.output, self.dependencies)
