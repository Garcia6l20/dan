import asyncio
from aiofiles import *
from aiofiles import os

import os as sync_os
import stat

from dan.core.pathlib import Path

async def _rmtree(path: Path):
    for root, dirs, files in sync_os.walk(path, topdown=False):
        clean_files = [os.remove(
            sync_os.path.join(root, name)) for name in files]
        clean_dirs = [os.rmdir(
            sync_os.path.join(root, name)) for name in dirs]
        await asyncio.gather(*clean_files)
        await asyncio.gather(*clean_dirs)
    await os.rmdir(path)

async def _remove_force(path: Path):
    sync_os.chmod(path, stat.S_IWRITE)
    await os.remove(path)

async def _rmtree_force(path: Path):
    for root, dirs, files in sync_os.walk(path, topdown=False):
        clean_files = [_remove_force(
            Path(root) / name) for name in files]
        clean_dirs = [os.rmdir(
            sync_os.path.join(root, name)) for name in dirs]
        await asyncio.gather(*clean_files)
        await asyncio.gather(*clean_dirs)
    await os.rmdir(path)

async def rmtree(path: Path, force=False):
    if force:
        await _rmtree_force(path)
    else:
        await _rmtree(path)

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
