import asyncio
from pathlib import Path
import os
import sys


class AsyncRunner:
    async def run(self, command, pipe=True):
        self.debug(f'executing: {command}')
        if pipe:
            stdout=asyncio.subprocess.PIPE
        else:
            stdout=None
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=stdout,
                                                                stderr=stdout)
        out, err = await proc.communicate()
        if proc.returncode != 0:
            self.error(f'running command: {command}\n{err.decode() if err else ""}')
            sys.exit(-1)
        return out, err


class chdir:
    def __init__(self, path: Path, create=True):
        self.path = path
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        self.prev = None

    def __enter__(self):
        self.prev = Path.cwd()
        os.chdir(self.path)
        return None

    def __exit__(self, *args):
        os.chdir(self.prev)
