from dataclasses import dataclass, field
from enum import Enum

from dan.core.pathlib import Path


class InstallMode(Enum):
    user = 0
    dev = 1


class BuildType(Enum):
    debug = 0
    release = 1
    release_min_size = 2
    release_debug_infos = 3

    @property
    def is_debug_mode(self):
        """Return true if the build type should produce debug symbols (ie.: debug and release_debug_infos)"""
        return self in (BuildType.debug, BuildType.release_debug_infos)

@dataclass(eq=True, unsafe_hash=True)
class InstallSettings:
    destination: str = '/usr/local'
    runtime_prefix: str = 'bin'
    libraries_prefix: str = 'lib'
    includes_prefix: str = 'include'
    data_prefix:str = 'share'
    create_pkg_config: bool = True

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

@dataclass
class ToolchainSettings:
    cxx_flags: list[str] = field(default_factory=lambda: list())

@dataclass
class Settings:
    build_type: BuildType = BuildType.debug
    install: InstallSettings = field(default_factory=lambda: InstallSettings())
    target: ToolchainSettings = field(default_factory=lambda: ToolchainSettings())


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
