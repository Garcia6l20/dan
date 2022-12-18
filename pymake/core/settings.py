from enum import Enum
from pymake.core.cache import SubCache

from pymake.core.pathlib import Path


class InstallMode(Enum):
    user = 0,
    dev = 1


class InstallSettings(SubCache):
    def __init__(self):
        self.destination = '/usr/local'
        self.runtime_prefix = 'bin'
        self.libraries_prefix = 'lib'
        self.includes_prefix = 'include'
        self.data_prefix = 'share'
        self.create_pkg_config = True

    @property
    def runtime_destination(self):
        return Path(self.destination).absolute() / self.runtime_prefix

    @property
    def libraries_destination(self):
        return Path(self.destination).absolute() / self.libraries_prefix

    @property
    def data_destination(self):
        return Path(self.destination).absolute() / self.data_prefix

    @property
    def includes_destination(self):
        return Path(self.destination).absolute() / self.includes_prefix


class Settings(SubCache):

    def __init__(self):
        self.install = InstallSettings()
