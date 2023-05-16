from click import Path
from dan.core import aiofiles
from dan.core.target import Target
import aiohttp
import tarfile


async def fetch_file(url, dest):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
            if resp.status != 200:
                raise RuntimeError(f'unable to fetch {url}: {data.decode()}')

    async with aiofiles.open(
        dest, "wb"
    ) as outfile:
        await outfile.write(data)


class TarSources(Target, internal=True):

    url: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.output: Path = self.build_path / 'sources'

    async def __build__(self):
        self.info(f'downloading {self.url}')
        archive_name = self.url.split("/")[-1]
        await fetch_file(self.url, self.build_path / archive_name)
        with tarfile.open(self.build_path / archive_name) as f:
            self.info(f'extracting {archive_name}')
            f.extractall(self.output)
