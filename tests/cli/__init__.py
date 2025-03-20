from contextlib import contextmanager
import unittest
import click.testing
import click
from pathlib import Path
import sys

from dan import logging
from dan.core import asyncio

import typing as t


class CliTestCase(unittest.TestCase, logging.Logging):
    tests_path = Path(__file__).parent
    root_path = tests_path.parent.parent
    examples_path = root_path / "examples"
    tmp_path = tests_path / "tmp"

    verbose_level = 2
    no_progress = True

    test_project: str = None
    base_command: click.BaseCommand = None

    @property
    def source_path(self):
        return self.examples_path / self.test_project

    def __init__(self, methodName: str = "runTest") -> None:
        assert self.test_project is not None
        assert self.base_command is not None
        self.fullname = "test-" + self.test_project.replace("/", "-")
        super().__init__(methodName)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.runner = click.testing.CliRunner(
            env={
                "DAN_SOURCE_PATH": self.source_path.as_posix(),
                "DAN_VERBOSE": str(self.verbose_level),
                "DAN_NOPROGRESS": str(self.no_progress),
            }
        )
        self.logger = self.get_logger()

    def setUp(self) -> None:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
        return super().setUp()

    @contextmanager
    def session(self):
        self.tmp_path.mkdir(exist_ok=True, parents=True)
        try:
            with self.runner.isolated_filesystem(self.tmp_path) as cwd:
                cwd = Path(cwd)
                self.runner.env["DAN_CACHE_PATH"] = cwd.as_posix()
                self.runner.env["DAN_BUILD_PATH"] = (cwd / "build").as_posix()
                yield cwd
        finally:
            cwd.rmdir(recursive=True)

    def assertExists(self, path: Path, msg: str = None):
        return self.assertTrue(path.exists(), msg)

    def assertChanged(
        self, path: Path, previous_modification_time: float, msg: str = None
    ):
        modif_time = path.modification_time
        self.assertGreater(modif_time, previous_modification_time, msg)
        return modif_time

    def invoke(
        self,
        args: t.Optional[t.Union[str, t.Sequence[str]]] = None,
        input: t.Optional[t.Union[str, bytes, t.IO]] = None,
        env: t.Optional[t.Mapping[str, t.Optional[str]]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        fail_test: bool = False,
        forward_exceptions: bool = False,
        msg: str = None,
        **extra: t.Any,
    ):
        result = self.runner.invoke(
            self.base_command, args, input, env, catch_exceptions, color, **extra
        )
        if result.exception and forward_exceptions:
            raise result.exception
        
        check = lambda rc: rc == 0 if not fail_test else lambda rc: rc != 0
        if check(result.return_value):
            standardMsg=f"command failure: {args=}, {input=}\n ==== stdout ==== \n{result.stdout}\n", # ==== stderr ==== \n{result.stderr}",
            msg = self._formatMessage(None, standardMsg)
            raise self.failureException(msg)
        
        sys.stdout.write(result.stdout)
        # sys.stderr.write(result.stderr)
        
        return result
