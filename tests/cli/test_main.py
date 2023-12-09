from tests.cli import CliTestCase
from dan.cli.main import cli

class DanIoTest(CliTestCase):

    test_project = 'cxx/dan.io'
    base_command = cli

    def test_cli_base(self):
        with self.session():
            self.invoke('configure -t default')
            self.invoke('ls targets')
            self.invoke('ls options')
            self.invoke('build -vv')

