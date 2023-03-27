from pymake.core.pathlib import Path
from pymake.core import asyncio
from pymake.core.target import Target, TargetDependencyLike
from typing import Callable
import inspect


class generator:
    def __init__(self, output: str, template: str, dependencies: TargetDependencyLike = list(), name=None):
        self.output = Path(output)
        self.dependencies = dependencies
        self.template = template

    def __call__(self, fn: Callable):
        class Generator(Target):
            def __init__(self, output: Path, template: str, dependencies: list[TargetDependencyLike] = list()) -> None:
                super().__init__(output.stem)
                self.output = output
                self.template = template
                self.load_dependencies(dependencies)
                self.load_dependency(template)

            def __call__(self):
                import jinja2
                arg_spec = inspect.getfullargspec(fn)
                args = list()
                kwargs = dict()
                if 'self' in arg_spec.args:
                    args.append(self)

                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(self.source_path))
                template = env.get_template(self.template)
                data = fn(*args, **kwargs)
                self.output.parent.mkdir(parents=True, exist_ok=True)
                print(template.render(data), file=open(self.output, 'w'))

        return Generator(self.output, self.template, self.dependencies)
