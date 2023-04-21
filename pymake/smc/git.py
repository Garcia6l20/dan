from pymake.core.pathlib import Path
from pymake.core import asyncio, aiofiles
from pymake.core.target import Target
from pymake.core.runners import async_run
from pymake.logging import Logging


class GitSources(Target, Logging):
    def __init__(self, name: str, url: str, refspec: str = None, patches: list[str] = list()) -> None:
        super().__init__(name, all=False)
        self.url = url
        self.refspec = refspec
        self.sha1 = None
        self.output: Path = self.build_path / 'sources'
        self.git_dir: Path = self.output / '.git'
        self.patches = patches

    @asyncio.cached
    async def initialize(self):
        await self.preload()

        if not self.clean_request:
            if not self.git_dir.exists():
                try:
                    self.output.mkdir()
                    await async_run(f'git init', logger=self, cwd=self.output)
                    await async_run(f'git config advice.detachedHead off', logger=self, cwd=self.output)
                    await async_run(f'git remote add origin {self.url}', logger=self, cwd=self.output)
                    await async_run(f'git fetch -q --depth 1 origin {self.refspec}', logger=self, cwd=self.output)
                    await async_run(f'git checkout FETCH_HEAD', logger=self, cwd=self.output)
                    
                    for patch in self.patches:
                        await async_run(f'git am {self.source_path / patch}', logger=self, cwd=self.output)

                except Exception as e:
                    await aiofiles.rmtree(self.output)
                    raise e

        return await super().initialize()

    async def __call__(self):
        return
