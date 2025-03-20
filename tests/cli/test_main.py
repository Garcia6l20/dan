from pathlib import Path
from tests.cli import CliTestCase
from dan.cli.main import cli


class DanIoTest(CliTestCase):

    test_project = "cxx/dan.io"
    base_command = cli
    env_name = "dan-testing"
    clean = True

    def setUp(self):
        super().setUp()

        if self.clean:
            try:
                self.invoke(f"env remove {self.env_name}", forward_exceptions=True)
            except FileNotFoundError:
                pass

        self.invoke(f"env new {self.env_name} -f")

    def tearDown(self):
        if self.clean:
            self.invoke(f"env remove {self.env_name}")

        super().tearDown()

    def test_cli_base(self):
        with self.session() as cwd:

            toolchains = self.invoke('get toolchains').stdout.splitlines()
            envs = self.invoke('env list').stdout.splitlines()

            #
            # configuration
            #

            self.invoke(f"configure {self.env_name}")

            targets = self.invoke('get targets').stdout.splitlines()
            self.assertIn("catch2-example", targets)
            self.assertIn("test-fmt", targets)

            options = self.invoke('get options').stdout.splitlines()

            #
            # initial build
            #

            self.invoke('build -vv')

            expected_build_path = cwd / "build" / self.env_name
            self.assertExists(expected_build_path)
            self.assertExists(expected_build_path / "bin")
            self.assertExists(expected_build_path / "bin" / "test-fmt")

            catch_example_bin = expected_build_path / "bin" / "catch2-example"
            self.assertExists(catch_example_bin)
            prev_modif_time = catch_example_bin.modification_time

            self.invoke('build -vv')
            self.assertEqual(prev_modif_time, catch_example_bin.modification_time)

            #
            # buildfile change -> rebuild
            #
            (self.source_path / "dan-build.py").touch()

            self.invoke('build -vv')
            prev_modif_time = self.assertChanged(catch_example_bin, prev_modif_time)

            #
            # source change -> rebuild
            #
            (self.source_path / "test_catch2.cpp").touch()

            self.invoke('build -vv')
            prev_modif_time = self.assertChanged(catch_example_bin, prev_modif_time)

            #
            # deduced dependency change -> rebuild
            #
            (self.source_path / "test.hpp").touch()

            self.invoke('build -vv')
            prev_modif_time = self.assertChanged(catch_example_bin, prev_modif_time)

            pass


if __name__ == "__main__":
    import unittest

    unittest.main()
