import asyncio
import os
import re
import typing as t

import aiofiles
from dan.core import asyncio
from dan.core.pathlib import Path
from dan.core.register import MakefileRegister
from dan.logging import Logging


class AsyncExecutable(Logging):
    async def execute(self, *args, **kwargs): ...


class Case:
    def __init__(self, name, *args, expected_result: int = 0, expected_output: str = None, file=None, lineno=None, strip_output=True, normalize_newlines=True):
        self.name = name
        self.args = args
        self.expected_result = expected_result
        self.file = file
        self.lineno = lineno
        self.expected_output = expected_output
        self.strip_output = strip_output
        self.normalize_newlines = normalize_newlines


class Test(Logging, MakefileRegister, internal=True):
    """Test definition
    """

    name: str = None
    fullname: str = None

    cases: t.Iterable[Case] = [Case(None, expected_result=0)]
    """Test cases
    
    list of args giving a return value
    """

    executable: type[AsyncExecutable] = None

    file: Path | str = None
    lineno: int = None

    def __init__(self, *args, **kwargs):
        # in case of inheritance usage, we must initialize the AsyncExecutable part
        super().__init__(*args, **kwargs)

        if self.name is None:
            self.name = self.__class__.__name__

        if not self.executable:
            if not hasattr(self, 'execute'):
                raise RuntimeError(
                    f'Test "{self.name}" does not have executable set, if you intent to use it through inheritance, make sure "Test" is the first derived class')
            self.executable = self
        elif isinstance(self.executable, type):
            self.executable = self.makefile.find(self.executable)

        self.name = self.name or self.executable.name
        self.fullname = f'{self.executable.makefile.fullname}.{self.name}'
        self.file = Path(self.file) if self.file else None
        self.workingDir = self.executable.build_path

    def basename(self, caze: Case):
        if len(self) <= 1:
            return self.name
        else:
            return f'{self.name}.{caze.name}'

    def outs(self, caze: Case):
        base = self.basename(caze)
        base = re.sub(r'[^\w_. -]', '_', base)
        out = self.workingDir / f'{base}.stdout'
        err = self.workingDir / f'{base}.stderr'
        return out, err

    async def _run_test(self, caze: Case):
        name = f'{self.name}.{caze.name}' if caze is not None else self.name
        args = [str(a) for a in caze.args]
        out, err, rc = await self.executable.execute(*args, no_raise=True, cwd=self.workingDir)
        out_log, out_err = self.outs(caze)
        async with aiofiles.open(out_log, 'w') as outlog, \
                aiofiles.open(out_err, 'w') as errlog:
            async with asyncio.TaskGroup(f'writing {name} log files') as group:
                group.create_task(outlog.write(out))
                group.create_task(errlog.write(err))
        if rc != caze.expected_result:
            out = out.strip()
            err = err.strip()
            msg = f'Test \'{name}\' failed (returned: {rc}, expected: {caze.expected_result}) !'
            if out:
                msg += '\nstdout: ' + out
            if err:
                msg += '\nstderr: ' + err
            raise RuntimeError(msg)

        if caze.expected_output is not None:

            if callable(caze.expected_output):
                expected_output = caze.expected_output(caze)
            else:
                expected_output = caze.expected_output

            if caze.strip_output:
                out = out.strip()

            if caze.normalize_newlines:
                out = out.replace(os.linesep, '\n')

            if isinstance(expected_output, re.Pattern):
                if not expected_output.match(out):
                    out = out.strip()
                    err = err.strip()
                    msg = f'Test \'{name}\' failed (output: {out}, expected: {expected_output}) !'
                    raise RuntimeError(msg)
            elif out != expected_output:
                out = out.strip()
                err = err.strip()
                msg = f'Test \'{name}\' failed (output: {out}, expected: {expected_output.strip()}) !'
                raise RuntimeError(msg)

    async def run_test(self):
        try:
            async with asyncio.TaskGroup(f'running {self.name} tests') as tests:
                for caze in self.cases:
                    tests.create_task(self._run_test(caze))
        except asyncio.ExceptionGroup as errors:
            for err in errors.errors:
                self.error(err)
            return False
        return True

    def __len__(self):
        return len(self.cases)
