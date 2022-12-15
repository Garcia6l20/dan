import logging
import sys
import tqdm
import asyncio
from pymake.core.pathlib import Path
import os
import subprocess
from collections.abc import Iterable


class CommandError(RuntimeError):
    def __init__(self, message, rc, stdout, stderr) -> None:
        super().__init__(message)
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr


_encoding = 'cp1252' if os.name == 'nt' else 'utf-8'


async def log_stream(stream, file=sys.stdout):
    while not stream.at_eof():
        data = await stream.readline()
        line = data.decode(_encoding)
        tqdm.tqdm.write(line, end='', file=file)


class AsyncRunner:
    async def run(self, command, pipe=True, no_raise=False, env=None, cwd=None):
        if not isinstance(command, str):
            command = ' '.join([f'"{arg}"' if isinstance(
                arg, Path) else arg for arg in command])
        self.debug(f'executing: {command}')
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=asyncio.subprocess.PIPE,
                                                                stderr=asyncio.subprocess.PIPE,
                                                                env=env,
                                                                cwd=cwd)
        if not pipe:
            create_task = asyncio.create_task
            return await asyncio.wait([create_task(log_stream(proc.stdout)),
                                       create_task(log_stream(proc.stderr, file=sys.stderr)),
                                       create_task(proc.wait())],
                                      return_when=asyncio.FIRST_COMPLETED)
        else:
            out, err = await proc.communicate()
            if proc.returncode != 0 and not no_raise:
                message = f'command returned {proc.returncode}: {command}\n{out.decode(_encoding) if out and len(out) else ""}\n{err.decode(_encoding) if err and len(err) else ""}'
                self.error(message)
                raise CommandError(message, proc.returncode, out, err)
            return out.decode(_encoding) if out else None, err.decode(_encoding) if err else None, proc.returncode


class SyncRunner:
    def run(self, command, pipe=True, no_raise=False, shell=True, env=None):
        # self.debug(f'executing: {command}')
        if pipe:
            stdout = subprocess.PIPE
        else:
            stdout = None
        proc = subprocess.Popen(command,
                                stdout=stdout,
                                stderr=stdout,
                                shell=shell,
                                env=env,
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


def unique(*seqs):
    seen = set()
    seen_add = seen.add
    full = list()
    for seq in seqs:
        full.extend(seq)
    return [x for x in full if not (x in seen or seen_add(x))]
