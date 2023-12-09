from pathlib import Path
from contextlib import nullcontext

import aiohttp

from dan.core import aiofiles


async def fetch_file(url, dest: Path, name: str = None, chunk_size=1024, progress=None):
    if name is None:
        name = dest.name
    timeout = aiohttp.ClientTimeout(
        total=30 * 60, connect=30, sock_connect=30, sock_read=None
    )
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                message = await resp.read()
                raise RuntimeError(f"unable to fetch {url}: {message.decode()}")
            size = int(resp.headers.get("content-length", 0))

            # with progress.Bar(
            #     f"downloading {name}", total=size // 1024, leave=False, unit="Ko"
            # ) as progressbar:
            with progress(f"downloading {name}", total=size // 1024) as bar:
                async with aiofiles.open(dest, mode="wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        await f.write(chunk)
                        bar(len(chunk) // 1024)
