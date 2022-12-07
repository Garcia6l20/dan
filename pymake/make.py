
import asyncio
import sys
from types import ModuleType

from pymake.core.include import targets, current_makefile
from pymake.logging import Logging

from pymake.core.target import Target
from pymake.cxx.targets import Executable


def make_target_name(name: str):
    return name.replace('_', '-')


class Make(Logging):
    def __init__(self, makefile : ModuleType = None, active_targets : list[str] = None):
        super().__init__('make')

        self.makefile = makefile or current_makefile

        self.active_targets: dict[str, Target] = dict()
        self.all_targets = targets()
                
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
        await asyncio.gather(*[target.__initialize__(name) for name, target in self.all_targets.items()])
        self.__initialized = True

    async def build(self):
        await self.initialize()
        await asyncio.gather(*[t.build() for t in self.active_targets.values()])
    
    @property
    def executable_targets(self) -> list[Executable]:
        return [exe for exe in self.active_targets.values() if isinstance(exe, Executable)]

    async def run(self):
        await self.initialize()
        await asyncio.gather(*[t.execute() for t in self.executable_targets])

    async def clean(self, target: str = None):
        await self.initialize()
        await asyncio.gather(*[t.clean() for t in self.active_targets.values()])
