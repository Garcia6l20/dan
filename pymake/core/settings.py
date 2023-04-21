from enum import Enum
from pymake.core.cache import SubCache

from pymake.core.pathlib import Path


class InstallMode(Enum):
    user = 0
    dev = 1


class BuildType(Enum):
    debug = 0
    release = 1
    release_min_size = 2
    release_debug_infos = 2


class InstallSettings(SubCache):
    def __init__(self, destination: str | Path = '/usr/local'):
        self.destination = str(destination)
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
        self.build_type = BuildType.debug
        self.install = InstallSettings()


def safe_load(name: str, value,  t: type):
    if t is not None and not isinstance(value, t):
        err = f'value {name} should be of type {t}'
        if type(value) == str:
            if issubclass(t, Enum):
                names = [n.lower()
                         for n in t._member_names_]
                value = value.lower()
                if value in names:
                    value = t(names.index(value))
                else:
                    err = f'option {name} should be one of {names}'
            else:
                import json
                value = json.loads(value)
            if not isinstance(value, t):
                raise RuntimeError(err)
        else:
            raise RuntimeError(err)
    return value
