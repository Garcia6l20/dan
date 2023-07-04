import asyncio
from aiofiles import *
from aiofiles import os

import os as sync_os
import stat
import re

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


async def sub(filepath, pattern, repl, **kwargs):
    async with open(filepath) as f:
        content = await f.read()
    content = re.sub(pattern, repl, content, **kwargs)
    async with open(filepath, 'w') as f:
        await f.write(content)

_lock_pool = None
def _get_lock_pool():
    global _lock_pool
    if _lock_pool is None:
        from concurrent.futures import ThreadPoolExecutor
        _lock_pool = ThreadPoolExecutor(max_workers=1)
    return _lock_pool

import lockfile

class LockFile(lockfile.LockFile):

    def __init__(self, path, timeout=None):
        super().__init__(path, False, timeout)
    
    def sync_acquire(self, timeout=None):
        return super().acquire(timeout)

    async def acquire(self, timeout=None):
        loop = asyncio.get_event_loop()
        def _acquire():
            return lockfile.LockFile.acquire(self, timeout)
        return await loop.run_in_executor(_get_lock_pool(), _acquire)
    
    def sync_release(self):
        return super().release()

    async def release(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_get_lock_pool(), super().release)
    
    async def __aenter__(self):
        await self.acquire()
       
    async def __aexit__(self, et, exc, tb):
        await self.release()
