from click import Path
from pymake.core import asyncio
from pymake.core.target import Target
from pymake.core.utils import AsyncRunner, chdir
from pymake.logging import Logging


class GitSources(Target, Logging, AsyncRunner):
    def __init__(self, name: str, url: str, refspec: str = None, patches: list[str] = list()) -> None:
        super().__init__(name, all=False)
        self.url = url
        self.refspec = refspec
        self.sha1 = None
        self.output: Path = self.build_path / 'sources'
        self.git_dir: Path = self.output / '.git'
        self.patches = patches

    @asyncio.once_method
    async def initialize(self):
        await self.preload()

        if not self.clean_request:
            if not self.git_dir.exists():
                _, _, rc = await self.run(f'git clone {self.url} {self.output}')
                assert rc == 0

            self.sha1 = (await self.run(f'git rev-parse {self.refspec}', cwd=self.output))[0].strip()
            current_sha1 = (await self.run(f'git rev-parse HEAD', cwd=self.output))[0].strip()
            if self.sha1 != current_sha1:
                await self.run(f'git checkout {self.sha1}', cwd=self.output)

                for patch in self.patches:
                    await self.run(f'git am {self.source_path / patch}', cwd=self.output)

        return await super().initialize(recursive_once=True)

    async def __call__(self):
        return
