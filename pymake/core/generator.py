from pymake.core.pathlib import Path
from pymake.core import asyncio
from pymake.core.target import Target, TargetDependencyLike
from typing import Callable
import inspect


class generator:
    def __init__(self, output: str, dependencies: TargetDependencyLike = None, name=None):
        self.output = Path(output)
        self.dependencies = dependencies

    def __call__(self, fn: Callable):
        class Generator(Target):
            def __init__(self, output: Path, dependencies: list[TargetDependencyLike] = list()) -> None:
                super().__init__(output.stem)
                self.output = output
                self.load_dependencies(dependencies)

            def __call__(self):
                arg_spec = inspect.getfullargspec(fn)
                args = list()
                kwargs = dict()
                if 'self' in arg_spec.args:
                    args.append(self)
                return fn(*args, **kwargs)
        return Generator(self.output, self.dependencies)
