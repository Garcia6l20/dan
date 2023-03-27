from click import Path
from pymake.core import asyncio
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
                _, _, rc = await async_run(f'git clone {self.url} {self.output}', logger=self)
                assert rc == 0

            self.sha1 = (await async_run(f'git rev-parse {self.refspec}', cwd=self.output, logger=self))[0].strip()
            current_sha1 = (await async_run(f'git rev-parse HEAD', cwd=self.output, logger=self))[0].strip()
            if self.sha1 != current_sha1:
                await async_run(f'git checkout {self.sha1}', cwd=self.output, logger=self)

                for patch in self.patches:
                    await async_run(f'git am {self.source_path / patch}', cwd=self.output, logger=self)

        return await super().initialize()

    async def __call__(self):
        return
