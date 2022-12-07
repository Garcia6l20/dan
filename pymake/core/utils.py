import asyncio
from pathlib import Path
import os
import sys


class CommandError(RuntimeError):
    def __init__(self, message, rc, stdout, stderr) -> None:
        super().__init__(message)
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr

class AsyncRunner:
    async def run(self, command, pipe=True, no_raise=False):
        self.debug(f'executing: {command}')
        if pipe:
            stdout=asyncio.subprocess.PIPE
        else:
            stdout=None
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=stdout,
                                                                stderr=stdout)
        out, err = await proc.communicate()
        if proc.returncode != 0 and not no_raise:
            message = f'command returned {proc.returncode}: {command}\n{err.decode() if err else ""}'
            self.error(message)
            raise CommandError(message, proc.returncode, out, err)
        return out.decode(), err.decode(), proc.returncode


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
