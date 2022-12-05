
import asyncio
import importlib.util
import logging
import sys

from click import Path
from pymake.core.logging import Logging

from pymake.core.target import Target


def make_target_name(name: str):
    return name.replace('_', '-')


class Make(Logging):
    def __init__(self, source_path: Path, active_targets : list[str] = None):
        super().__init__('make')

        self.source_path = source_path
        self.module_path = self.source_path / 'makefile.py'
        spec = importlib.util.spec_from_file_location(
            'makefile', self.module_path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.active_targets: dict[str, Target] = dict()

        self.all_targets: dict[str, Target] = dict()

        for k, v in self.module.__dict__.items():
            if isinstance(v, Target):
                self.all_targets[k] = v
                
        for name, target in self.all_targets.items():
            if name not in self.all_targets:
                self.error(f'Unknown target {name}')
                sys.exit(-1)
            self.active_targets[name] = target

        self.debug(f'targets: {self.all_targets}')
        self.__initialized = False
        
    async def initialize(self):
        if self.__initialized:
            return
        await asyncio.gather(*[target.__initialize__(name) for name, target in self.active_targets.items()])
        self.__initialized = True

    async def build(self):
        await self.initialize()
        await asyncio.gather(*[t.build() for t in self.active_targets.values()])

    async def clean(self, target: str = None):
        await self.initialize()
        await asyncio.gather(*[t.clean() for t in self.active_targets.values()])
