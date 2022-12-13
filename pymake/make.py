
import logging
from pathlib import Path
import sys
from tqdm import tqdm

from pymake.core.cache import Cache
from pymake.core.include import include
from pymake.core import asyncio
from pymake.cxx import init_toolchains
from pymake.logging import Logging
from pymake.core.target import Target
from pymake.cxx.targets import Executable


def make_target_name(name: str):
    return name.replace('_', '-')


class Make(Logging):
    _config_name = 'pymake.config.yaml'
    _cache_name = 'pymake.cache.yaml'

    def __init__(self, path: str, targets: list[str] = None, verbose: bool = False):
        logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)

        super().__init__('make')

        self.config = None
        self.cache = None
        path = Path(path)
        if not path.exists() or not (path / 'makefile.py').exists():
            self.source_path = Path.cwd().absolute()
            self.build_path = path.absolute().resolve()
        else:
            self.source_path = path.absolute().resolve()
            self.build_path = Path.cwd().absolute()

        self.config_path = self.build_path / self._config_name
        self.cache_path = self.build_path / self._cache_name

        self.required_targets = targets
        self.build_path.mkdir(exist_ok=True, parents=True)
        sys.pycache_prefix = str(self.build_path / '__pycache__')
        self.config = Cache(self.config_path)
        self.cache = Cache(self.cache_path)

        import pymake.core.globals
        pymake.core.globals.cache = self.cache

        self.debug(f'source path: {self.source_path}')
        self.debug(f'build path: {self.build_path}')

        assert (self.source_path /
                'makefile.py').exists(), f'no makefile in {self.source_path}'
        assert (self.source_path !=
                self.build_path), f'in-source build are not allowed'

    def configure(self, toolchain, build_type):
        if not self.config:
            self.config = dict()
        self.config.source_path = str(self.source_path)
        self.config.build_path = str(self.build_path)
        self.config.toolchain = toolchain
        self.config.build_type = build_type

    @asyncio.once_method
    async def initialize(self):
        assert self.source_path and self.config_path.exists(), 'configure first'

        toolchain = self.config.toolchain
        build_type = self.config.build_type
        init_toolchains(toolchain)
        self.info(f'using \'{toolchain}\' in \'{build_type}\' mode')
        include(self.source_path, self.build_path)

        from pymake.cxx import target_toolchain
        target_toolchain.set_mode(build_type)

        self.active_targets: dict[str, Target] = dict()
        
        if self.required_targets and len(self.required_targets) > 0:
            for target in Target.all:
                if target.name in self.required_targets or target.fullname in self.required_targets:
                    self.active_targets[target.fullname] = target
        else:
            for target in Target.all:
                self.active_targets[target.fullname] = target

        self.debug(f'targets: {[name for name in self.active_targets.keys()]}')

    @property
    def toolchains(self):
        from pymake.cxx.detect import get_toolchains
        return get_toolchains()

    async def build(self):
        await self.initialize()
        target_count = len(self.active_targets)
        pbar = tqdm(total=target_count, desc='building')
        tsks = list()
        def on_done(*args, **kwargs):
            pbar.update()
        for t in self.active_targets.values():
            tsk = asyncio.create_task(t.build())
            tsk.add_done_callback(on_done)
            tsks.append(tsk)

        await asyncio.gather(*tsks)

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
        await self.initialize()
        await asyncio.gather(*[t.execute() for t in self.executable_targets])

    async def clean(self, target: str = None):
        await self.initialize()
        from pymake.cxx import toolchain
        toolchain.scan = False
        from pymake.core.target import Target
        Target.clean_request = True
        await asyncio.gather(*[t.clean() for t in self.active_targets.values()])
        from pymake.cxx import target_toolchain

        target_toolchain.compile_commands.clear()
