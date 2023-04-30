from pymake.core.pathlib import Path
from pymake.core import asyncio
from pymake.core.target import Target, TargetDependencyLike
from typing import Callable
import inspect


class generator:
    def __init__(self, output: str, dependencies: TargetDependencyLike = list(), name=None):
        self.output = Path(output)
        self.dependencies = dependencies

    def __call__(self, fn: Callable):
        class Generator(Target):
            output = self.output
            dependencies = set(self.dependencies)

            def __build__(self):
                arg_spec = inspect.getfullargspec(fn)
                if 'self' in arg_spec.args:
                    return fn(self)
                elif not arg_spec.args:
                    return fn()
                else:
                    raise RuntimeError("Only 'self' is allowed as Generator argument")

        # hack the module location (used for Makefile's Targets resolution)
        Generator.__module__ = fn.__module__
        return Generator
