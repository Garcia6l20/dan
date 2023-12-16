import unittest
import click.testing
import click
from pathlib import Path
import sys

from dan import logging

import typing as t


class CliTestCase(unittest.TestCase, logging.Logging):
    tests_path = Path(__file__).parent
    root_path = tests_path.parent.parent
    examples_path = root_path / "examples"
    build_path = tests_path / "build-unittest"

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
        self.runner = click.testing.CliRunner(
            env={
                "DAN_BUILD_PATH": self.build_path.as_posix(),
                "DAN_SOURCE_PATH": self.source_path.as_posix(),
                "DAN_VERBOSE": str(self.verbose_level),
                "DAN_NOPROGRESS": str(self.no_progress),
            }
        )
        self.logger = self.get_logger()

    def setUp(self) -> None:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
        return super().setUp()

    def session(self):
        return self.runner.isolated_filesystem()

    def invoke(
        self,
        args: t.Optional[t.Union[str, t.Sequence[str]]] = None,
        input: t.Optional[t.Union[str, bytes, t.IO]] = None,
        env: t.Optional[t.Mapping[str, t.Optional[str]]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        fail_test: bool = False,
        **extra: t.Any,
    ):
        result = self.runner.invoke(
            self.base_command, args, input, env, catch_exceptions, color, **extra
        )
        (self.assertNotEqual if fail_test else self.assertEqual)(
            result.exit_code, 0, msg=f"command failure: {args=}, {input=}\n ==== output ==== \n{result.output}"
        )
        return result
