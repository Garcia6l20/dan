from dan.core.cache import Cache
from dan.core.paths import DAN_PATH, Path
from dan.cxx.base_toolchain import ToolchainSettings as CXXSettings

from dataclasses import dataclass
from dataclasses_json import dataclass_json
from functools import cached_property


ENVIRONMENTS_PATH = DAN_PATH / "environments"


@dataclass_json
@dataclass
class Environment:

    name: str
    cxx_toolchain: str
    cxx_settings: CXXSettings = CXXSettings()

    @property
    def path(self):
        return ENVIRONMENTS_PATH / self.name

    @property
    def system_packages_path(self):
        return self.path / "system-packages"
    
    @property
    def source_path(self):
        return self.path / "src"
    
    @property
    def build_path(self):
        return self.path / "build"
    
    @property
    def packages_path(self):
        return self.path / "packages"
    
    @property
    def package_search_paths(self):
        return [self.packages_path / "lib", self.system_packages_path]
    
    @cached_property
    def system_packages(self):
        from dan.pkgconfig.package import PkgConfig
        packages = []
        for pkg in self.system_packages_path.iterdir():
            packages.append(PkgConfig(pkg))
        return packages

    @cached_property
    def cache(self):
        return EnvironmentCache.instance(
            self.path / ".cache", cache_name=f"{self.name}-env", data=self
        )

    def __str__(self):
        return f"Environment({self.name})"

    @classmethod
    def available(cls):
        return [
            env.name for env in DAN_PATH.joinpath("environments").iterdir() if env.is_dir()
        ]

    @classmethod
    def load(cls, name: str):
        path = ENVIRONMENTS_PATH / name / ".cache"
        if not path.exists():
            raise FileNotFoundError(f"Environment '{name}' not found.")
        return EnvironmentCache.instance(path, cache_name=f"{name}-env").data


class EnvironmentCache(Cache[Environment]):
    indent = 2
