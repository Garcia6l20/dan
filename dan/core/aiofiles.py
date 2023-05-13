import asyncio
from aiofiles import *
from aiofiles import os

import os as sync_os

from dan.core.pathlib import Path

async def rmtree(path):
    for root, dirs, files in sync_os.walk(path, topdown=False):
        clean_files = [os.remove(
            sync_os.path.join(root, name)) for name in files]
        clean_dirs = [os.rmdir(
            sync_os.path.join(root, name)) for name in dirs]
        await asyncio.gather(*clean_files)
        await asyncio.gather(*clean_dirs)
    await os.rmdir(path)

async def copy(src : Path, dest : Path, chunk_size=2048):
    if dest.is_dir():
        dest = dest / src.name
    dest.parent.mkdir(exist_ok=True, parents=True)
    async with open(src, 'rb') as s,\
               open(dest, 'wb') as d:
        while True:
            chunk = await s.read(chunk_size)
            if len(chunk) == 0:
                break
            await d.write(chunk)
    dest.chmod(src.stat().st_mode)
