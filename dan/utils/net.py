
from pathlib import Path

import aiohttp
import tqdm

from dan.core import aiofiles


async def fetch_file(url, dest: Path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                message = await resp.read()
                raise RuntimeError(f'unable to fetch {url}: {message.decode()}')
            size = int(resp.headers.get('content-length', 0))

            with tqdm.tqdm(
                desc=f'downloading {dest.name}', total=size // 1024, leave=False, unit='Ko'
            ) as progressbar:
                async with aiofiles.open(dest, mode='wb') as f:
                    async for chunk in resp.content.iter_chunked(1024):
                        await f.write(chunk)
                        progressbar.update(len(chunk) // 1024)
