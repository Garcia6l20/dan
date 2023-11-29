import aiofiles
from dan.core.pathlib import Path
from dan.core.target import Target, TargetDependencyLike
from dan.core import asyncio
from typing import Callable
import inspect


class generator:
    def __init__(self, output: str, template: str, dependencies: TargetDependencyLike = None, options: dict = None):
        self.output = Path(output)
        self.dependencies = list() if dependencies is None else dependencies
        self.template = template
        self.options = dict() if options is None else options

    def __call__(self, fn: Callable):
        class JinjaGenerator(Target):
            name = self.output.stem
            output = self.output
            template = self.template
            dependencies = [*self.dependencies, self.template]
            options = self.options

            async def __build__(self):
                import jinja2
                arg_spec = inspect.getfullargspec(fn)
                if 'self' in arg_spec.args:
                    data = await asyncio.may_await(fn(self))
                elif not arg_spec.args:
                    data = await asyncio.may_await(fn())
                else:
                    raise RuntimeError(
                        "Only 'self' is allowed as Generator argument")
                self.output.parent.mkdir(parents=True, exist_ok=True)
                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(self.source_path))
                template = env.get_template(self.template)
                async with aiofiles.open(self.output, 'w') as out:
                    await out.write(template.render(data))

        # hack the module location (used for Makefile's Targets resolution)
        JinjaGenerator.__module__ = fn.__module__
        return JinjaGenerator
