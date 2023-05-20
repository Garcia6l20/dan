import os
from click import Path
import tqdm
from dan.core import aiofiles, asyncio
from dan.core.target import Target
import aiohttp
import tarfile
import zipfile


async def fetch_file(url, dest: Path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                message = resp.read()
                raise RuntimeError(f'unable to fetch {url}: {message.decode()}')
            size = int(resp.headers.get('content-length', 0))

            with tqdm.tqdm(
                desc=f'downloading {dest.name}', total=size // 1024, leave=False, unit='Ko'
            ) as progressbar:
                async with aiofiles.open(dest, mode='wb') as f:
                    async for chunk in resp.content.iter_chunked(1024):
                        await f.write(chunk)
                        progressbar.update(len(chunk) // 1024)


class TarSources(Target, internal=True):

    url: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.output: Path = 'sources'

    async def __build__(self):
        self.info(f'downloading {self.url}')
        archive_name = self.url.split("/")[-1]
        await fetch_file(self.url, self.build_path / archive_name)
        self.info(f'extracting {archive_name}')
        if archive_name.endswith('.zip'):
            with zipfile.ZipFile(self.build_path / archive_name) as f:
                root = os.path.commonprefix(f.namelist())
                f.extractall(self.output.parent)
        else:
            with tarfile.open(self.build_path / archive_name) as f:
                root = os.path.commonprefix(f.getnames())
                f.extractall(self.output.parent)
        async with asyncio.TaskGroup() as g:
            g.create_task(aiofiles.os.rename(self.output.parent / root, self.output))
            g.create_task(aiofiles.os.remove(self.build_path / archive_name))
