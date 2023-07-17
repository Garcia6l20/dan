import os
import tempfile
from pathlib import Path
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
    archive_name: str = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.output = str(self.name)

    def __extract__(self, archive_path: Path, dest: Path):
        if archive_path.suffix == '.zip':
            with zipfile.ZipFile(archive_path) as f:
                root = os.path.commonprefix(f.namelist())
                f.extractall(dest)
        else:
            mode = 'r:*'
            if len(archive_path.suffixes) and archive_path.suffixes[-1] == '.xz':
                mode = 'r:xz'
            with tarfile.open(archive_path, mode) as f:
                root = os.path.commonprefix(f.getnames())
                f.extractall(dest)
        return root

    async def __build__(self):
        archive_name = self.archive_name or self.url.split("/")[-1]
        archive_path = self.build_path / archive_name
        if archive_path.exists():
            self.debug('%s already available (download skipped)', archive_path)
        else:
            self.info(f'downloading {self.url}')
            await fetch_file(self.url, self.build_path / archive_name)
        with tempfile.TemporaryDirectory(prefix=f'{self.name}-') as tmp_dest:
            extract_dest = Path(tmp_dest) / 'a'
            self.info(f'extracting {archive_name}')
            root = await asyncio.get_event_loop().run_in_executor(None, self.__extract__, archive_path, extract_dest)
            max_try_count = 5
            try_count = 0
            while True:
                try:
                    await aiofiles.os.renames(extract_dest / root, self.output)
                    break
                except PermissionError as err:
                    # NOTE: under windows, moving folders may fail because of "Quick Access" using it
                    #       this is a dumb workaround
                    try_count += 1
                    if try_count < max_try_count:
                        self.warning('failed to move source directory: %s, retrying...', err)
                        await asyncio.sleep(0.02)
                    else:
                        self.error('still failing to move source directory (after %d attempts): %s', max_try_count, err)
                        raise err

            await aiofiles.os.remove(archive_path)
