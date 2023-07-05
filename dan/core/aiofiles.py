import asyncio
from aiofiles import *
from aiofiles import os

import os as sync_os
import stat
import re
import sys
import errno
import contextlib
import time

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



class FileLock:
    def __init__(self, path: str|Path, timeout=None, poll_interval=0.1) -> None:
        self._path = Path(path)
        self._mode: int = 0o644
        self._fh = None
        self._timeout = timeout
        self._poll_interval = poll_interval

    def __del__(self):
        if self.has_lock:
            self.release()

    @property
    def locked(self):
        return self._path.exists()

    @property
    def has_lock(self):
        return self._fh is not None

    def try_acquire(self):
        flags = (
            sync_os.O_WRONLY  # open for writing only
            | sync_os.O_CREAT
            | sync_os.O_EXCL  # together with above raise EEXIST if the file specified by filename exists
            | sync_os.O_TRUNC  # truncate the file to zero byte
        )
        try:
            self._fh = sync_os.open(self._path, flags, self._mode)
            return True
        except OSError as exception:  # re-raise unless expected exception
            if not (
                exception.errno == errno.EEXIST  # lock already exist
                or (exception.errno == errno.EACCES and sys.platform == "win32")  # has no access to this lock
            ):  # pragma: win32 no cover
                raise
            return False

    async def acquire(self, timeout=None):
        if timeout is None:
            timeout = self._timeout
        t0 = t1 = time.perf_counter()
        while timeout is None or timeout < t1 - t0:
            if self.try_acquire():
                return True
            await asyncio.sleep(self._poll_interval)
            t1 = time.perf_counter()
        return False

    def release(self):
        assert self._fh is not None
        sync_os.close(self._fh)
        self._fh = None
        with contextlib.suppress(OSError):  # the file is already deleted and that's what we want
            self._path.unlink()

    async def __aenter__(self):
        await self.acquire()
    
    async def __aexit__(self, *exc):
        self.release()
