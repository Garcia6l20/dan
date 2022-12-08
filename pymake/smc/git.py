from click import Path
from pymake.core import asyncio
from pymake.core.target import Target
from pymake.core.utils import AsyncRunner, chdir
from pymake.logging import Logging


class GitSources(Target, Logging, AsyncRunner):
    def __init__(self, name: str, url: str, refspec: str = None) -> None:
        super().__init__(name)
        self.url = url
        self.refspec = refspec
        self.output: Path = self.build_path / self.sname
        self.git_dir: Path = self.output / '.git'

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        if not self.clean_request:
            if not self.git_dir.exists():
                await self.run(f'git clone {self.url} {self.output}', pipe=False)
            with chdir(self.output):
                await self.run(f'git checkout {self.refspec}', pipe=False)
                await self.run(f'git reset --hard', pipe=False)
        return await super().initialize(recursive_once=True)

    async def __call__(self):
        pass
