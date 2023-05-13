import aiofiles
from dan.core.pathlib import Path
from dan.core import asyncio
from dan.core.target import Target, TargetDependencyLike
from typing import Callable
import inspect


class generator:
    def __init__(self, output: str, template: str, dependencies: TargetDependencyLike = list(), name=None):
        self.output = Path(output)
        self.dependencies = dependencies
        self.template = template

    def __call__(self, fn: Callable):
        class JinjaGenerator(Target):
            name = self.output.stem
            output = self.output
            template = self.template
            dependencies = [*self.dependencies, self.template]

            async def __build__(self):
                import jinja2
                arg_spec = inspect.getfullargspec(fn)
                if 'self' in arg_spec.args:
                    data = fn(self)
                elif not arg_spec.args:
                    data = fn()
                else:
                    raise RuntimeError(
                        "Only 'self' is allowed as Generator argument")
                if inspect.isawaitable(data):
                    data = await data
                self.output.parent.mkdir(parents=True, exist_ok=True)
                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(self.source_path))
                template = env.get_template(self.template)
                async with aiofiles.open(self.output, 'w') as out:
                    await out.write(template.render(data))

        # hack the module location (used for Makefile's Targets resolution)
        JinjaGenerator.__module__ = fn.__module__
        return JinjaGenerator
