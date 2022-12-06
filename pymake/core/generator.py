from pymake.core.target import Target, TargetDependencyLike
from typing import Callable
import inspect

class generator:
    def __init__(self, output: str, dependencies: TargetDependencyLike = None, name=None):
        self.output = output
        self.dependencies = dependencies

    def __call__(self, fn: Callable):
        class Generator(Target):
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
        return Generator(self.output, self.dependencies)
