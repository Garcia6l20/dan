
import io
import logging
import os
import subprocess
import sys

import tqdm

import asyncio


class CommandError(RuntimeError):
    def __init__(self, message, rc, stdout, stderr) -> None:
        super().__init__(message)
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr


_encoding = 'cp1252' if os.name == 'nt' else 'utf-8'


async def log_stream(stream, *files):
    while not stream.at_eof():
        data = await stream.readline()
        line = data.decode(_encoding)
        for file in files:
            if file in [sys.stdout, sys.stderr]:
                tqdm.tqdm.write(line, end='', file=file)
            else:
                file.write(line)

_jobs_sem: asyncio.Semaphore = None


def max_jobs(count=1):
    global _jobs_sem
    if count > 0:
        _jobs_sem = asyncio.Semaphore(count)
    else:
        _jobs_sem = None

def cmdline2list(s: str):
    """
    Translate a command line string into a sequence of arguments,
    using the same rules as the MS C runtime:

    1) Arguments are delimited by white space, which is either a
       space or a tab.

    2) A string surrounded by double quotation marks is
       interpreted as a single argument, regardless of white space
       contained within.  A quoted string can be embedded in an
       argument.

    3) A double quotation mark preceded by a backslash is
       interpreted as a literal double quotation mark.

    4) Backslashes are interpreted literally, unless they
       immediately precede a double quotation mark.

    5) If backslashes immediately precede a double quotation mark,
       every pair of backslashes is interpreted as a literal
       backslash.  If the number of backslashes is odd, the last
       backslash escapes the next double quotation mark as
       described in rule 3.
    """
    result = []
    current = []
    quote = None
    escaped = False
    for c in s:
        match c:
            case ' ' | '\t':
                if escaped:
                    current.append(c)
                    escaped = False
                else:
                    if quote is None:
                        if current:
                            result.append(''.join(current))
                            current = []
                    else:
                        current.append(c)
            case "'" | '"':
                if escaped:
                    current.append(c)
                    escaped = False
                else:                    
                    if quote is not None and quote == c:
                        quote = None
                    else:
                        quote = c
            case '\\':
                if escaped:
                    current.append('\\')
                escaped = True
            case _:
                if escaped:
                    current.append('\\')
                current.append(c)
                escaped = False

    if current:
        result.append(''.join(current))

    return result

async def async_run(command, log=True, logger: logging.Logger = None, no_raise=False, env=None, cwd=None):
    if _jobs_sem is not None:
        await _jobs_sem.acquire()
    try:
        if not isinstance(command, str):
            command = subprocess.list2cmdline(command)
        if env:
            e = dict(os.environ)
            for k, v in env.items():
                e[k] = v
            env = e
        if logger:
            logger.debug(f'executing: {command}')
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=asyncio.subprocess.PIPE,
                                                                stderr=asyncio.subprocess.PIPE,
                                                                env=env,
                                                                cwd=cwd)

        out = io.StringIO()
        err = io.StringIO()
        outs = [out]
        errs = [err]
        if log:
            outs.append(sys.stdout)
            errs.append(sys.stderr)

        await asyncio.gather(
            log_stream(proc.stdout, *outs),
            log_stream(proc.stderr, *errs),
            proc.wait())
        # make sure return code is available
        await proc.communicate()
        out = out.getvalue()
        err = err.getvalue()
        if proc.returncode != 0 and not no_raise:
            message = f'command returned {proc.returncode}: {command}\n{out}\n{err}'
            if logger:
                logger.error(message)
            raise CommandError(message, proc.returncode, out, err)
        return out, err, proc.returncode
    finally:
        if _jobs_sem is not None:
            _jobs_sem.release()


def sync_run(command, pipe=True, logger: logging.Logger = None, no_raise=False, shell=True, env=None, cwd=None):
    if not isinstance(command, str):
        command = subprocess.list2cmdline(command)
    if pipe:
        stdout = subprocess.PIPE
    else:
        stdout = None
    if logger:
        logger.debug(f'executing: {command}')
    proc = subprocess.Popen(command,
                            stdout=stdout,
                            stderr=stdout,
                            shell=shell,
                            env=env,
                            cwd=cwd,
                            universal_newlines=True)
    out, err = proc.communicate()
    if proc.returncode != 0 and not no_raise:
        message = f'command returned {proc.returncode}: {command}\n{err if err else ""}'
        if logger:
            logger.error(message)
        raise CommandError(message, proc.returncode, out, err)
    return out if out else None, err if err else None, proc.returncode
