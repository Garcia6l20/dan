import asyncio
import re
import typing as t

import aiofiles
from pymake.core import asyncio
from pymake.core.pathlib import Path
from pymake.logging import Logging


class AsyncExecutable(Logging):
    async def execute(self, *args, **kwargs): ...


class Test(Logging):
    """Test definition
    """

    name: str = None
    fullname: str = None

    cases: t.Iterable[tuple[t.Iterable[t.Any], int]] = [((), 0)]
    """Test cases
    
    list of args giving a return value
    """

    executable: type[AsyncExecutable] = None

    file: Path | str = None
    lineno: int = None

    makefile: None

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
            self.executable = self.executable()

        self.name = self.name or self.executable.name
        self.fullname = f'{self.executable.makefile.fullname}.{self.name}'
        self.file = Path(self.file) if self.file else None
        self.workingDir = self.executable.build_path

    def basename(self, args, expected_result):
        if len(self) <= 1:
            return self.name
        else:
            base = self.name
            if len(args) > 0:
                base += f'-{"-".join([str(a) for a in args])}'
            if expected_result != 0:
                base += f'-{expected_result}'
            return base

    def outs(self, args, expected_result):
        base = self.basename(args, expected_result)
        base = re.sub(r'[^\w_. -]', '_', base)
        out = self.workingDir / f'{base}.stdout'
        err = self.workingDir / f'{base}.stderr'
        return out, err

    async def _run_test(self, args, expected_result=0):
        args = [str(a) for a in args]
        out, err, rc = await self.executable.execute(*args, no_raise=True, cwd=self.workingDir)
        out_log, out_err = self.outs(args, expected_result)
        async with aiofiles.open(out_log, 'w') as outlog, \
                aiofiles.open(out_err, 'w') as errlog:
            async with asyncio.TaskGroup() as group:
                group.create_task(outlog.write(out))
                group.create_task(errlog.write(err))
        if rc != expected_result:
            out = out.strip()
            err = err.strip()
            msg = f'Test \'{self.name}\' failed (returned: {rc}, expected: {expected_result}) !'
            if out:
                msg += '\nstdout: ' + out
            if err:
                msg += '\nstderr: ' + err
            raise RuntimeError(msg)

    async def run_test(self):
        try:
            async with asyncio.TaskGroup() as tests:
                for args, expected_result in self.cases:
                    tests.create_task(self._run_test(
                        args, expected_result=expected_result))
        except asyncio.ExceptionGroup as errors:
            for err in errors.errors:
                self.error(err)
            return False
        return True

    def __len__(self):
        return len(self.cases)
