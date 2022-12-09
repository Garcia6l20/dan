import asyncio
from pathlib import Path
import os
import subprocess
from collections.abc import Iterable


class CommandError(RuntimeError):
    def __init__(self, message, rc, stdout, stderr) -> None:
        super().__init__(message)
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr


class AsyncRunner:
    async def run(self, command, pipe=True, no_raise=False, env=None, cwd=None):
        if not isinstance(command, str):
            command = ' '.join([f'"{arg}"' if isinstance(arg, Path) else arg for arg in command])
        self.debug(f'executing: {command}')
        if pipe:
            stdout = asyncio.subprocess.PIPE
        else:
            stdout = None
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=stdout,
                                                                stderr=stdout,
                                                                env=env,
                                                                cwd=cwd)
        out, err = await proc.communicate()
        enc = 'cp1252' if os.name =='nt' else 'utf-8'
        if proc.returncode != 0 and not no_raise:
            message = f'command returned {proc.returncode}: {command}\n{out.decode(enc) if out and len(out) else ""}\n{err.decode(enc) if err and len(err) else ""}'
            self.error(message)
            raise CommandError(message, proc.returncode, out, err)
        return out.decode(enc) if out else None, err.decode(enc) if err else None, proc.returncode


class SyncRunner:
    def run(self, command, pipe=True, no_raise=False, shell=True):
        # self.debug(f'executing: {command}')
        if pipe:
            stdout = subprocess.PIPE
        else:
            stdout = None
        proc = subprocess.Popen(command,
                                stdout=stdout,
                                stderr=stdout,
                                shell=shell,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.returncode != 0 and not no_raise:
            message = f'command returned {proc.returncode}: {command}\n{err if err else ""}'
            self.error(message)
            raise CommandError(message, proc.returncode, out, err)
        return out if out else None, err if err else None, proc.returncode


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
