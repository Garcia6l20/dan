
import importlib.util
import logging

from click import Path
from pymake.core.logging import Logging

from pymake.core.target import Target

def make_target_name(name : str):
    return name.replace('_', '-')

class Make(Logging):
    def __init__(self, source_path: Path):
        super().__init__('make')

        self.source_path = source_path
        self.module_path = self.source_path / 'pymakefile.py'
        spec = importlib.util.spec_from_file_location(
            'pymakefile', self.module_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

        self.targets: dict[str, Target] = dict()

        for k, v in self.module.__dict__.items():
            if isinstance(v, Target):
                self.targets[k] = v  
                if not v.name:
                    v.name = make_target_name(k)

        self.debug(f'targets: {self.targets}')

    async def build(self):
        self.info(f'building {self.source_path}')
        for name, target in self.targets.items():
            await target.build()
