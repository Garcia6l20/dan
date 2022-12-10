
from pathlib import Path
import sys

from pymake.core.include import targets, include
from pymake.core import asyncio
from pymake.cxx import init_toolchains
from pymake.logging import Logging

from pymake.core.target import Target
from pymake.cxx.targets import Executable


def make_target_name(name: str):
    return name.replace('_', '-')


class Make(Logging):
    def __init__(self, mode: str = 'release', toolchain: str = None, active_targets: list[str] = None):
        super().__init__('make')

        init_toolchains(toolchain)

        include(Path.cwd())


        from pymake.cxx import target_toolchain
        target_toolchain.set_mode(mode)

        self.active_targets: dict[str, Target] = dict()
        self.all_targets = targets()

        for name, target in self.all_targets.items():
            if name not in self.all_targets:
                self.error(f'Unknown target {name}')
                sys.exit(-1)
            self.active_targets[name] = target
            target.name = name

        self.debug(f'targets: {self.all_targets}')

    @property
    def toolchains(self):
        from pymake.cxx.detect import get_toolchains
        return get_toolchains()

    async def build(self):
        await asyncio.gather(*[t.build() for t in self.active_targets.values()])

    @property
    def executable_targets(self) -> list[Executable]:
        return [exe for exe in self.active_targets.values() if isinstance(exe, Executable)]

    async def scan_toolchains(self, script: Path = None):
        from pymake.cxx.detect import create_toolchains, load_env_toolchain
        if script:
            load_env_toolchain(script)
        else:
            create_toolchains(script)

    async def run(self):
        await asyncio.gather(*[t.execute() for t in self.executable_targets])

    async def clean(self, target: str = None):
        from pymake.cxx import toolchain
        toolchain.scan = False
        from pymake.core.target import Target
        Target.clean_request = True
        await asyncio.gather(*[t.clean() for t in self.active_targets.values()])
        from pymake.cxx import target_toolchain

        target_toolchain.compile_commands.clear()
