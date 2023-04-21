from click import Path
from pymake.core import asyncio, aiofiles
from pymake.core.target import Target
from pymake.logging import Logging
import aiohttp
import tarfile


async def fetch_file(url, dest):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            assert resp.status == 200
            data = await resp.read()

    async with aiofiles.open(
        dest, "wb"
    ) as outfile:
        await outfile.write(data)


class TarSources(Target, Logging):
    def __init__(self, name: str, url: str, version: str = None) -> None:
        super().__init__(name, version=version, all=False)
        self.url = url
        self.archive_name = url.split("/")[-1]
        self.output: Path = self.build_path / 'sources'

    async def __call__(self):
        self.info(f'downloading {self.url}')
        await fetch_file(self.url, self.build_path / self.archive_name)
        with tarfile.open(self.build_path / self.archive_name) as f:
            self.info(f'extracting {self.archive_name}')
            f.extractall(self.output)
