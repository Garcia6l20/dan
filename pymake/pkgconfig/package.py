from pathlib import Path
import re
import pkgconfig

from pymake.core.find import find_file, library_paths_lookup
from pymake.cxx.targets import CXXTarget


class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def find_pkg_config(name, paths=list()) -> Path:
    return find_file(fr'.*{name}\.pc', ['$PKG_CONFIG_PATH', *paths, *library_paths_lookup])


class Package(CXXTarget):
    def __init__(self, name, search_paths: list[str] = list()) -> None:
        self.output = None
        self.config_path = find_pkg_config(name, search_paths)
        if not self.config_path:
            raise MissingPackage(name)
        with open(self.config_path) as f:
            lines = [l for l in [l.strip().removesuffix('\n')
                                 for l in f.readlines()] if len(l)]
            for line in lines:
                pos = line.find('=')
                if pos > 0:
                    k = line[:pos].strip()
                    v = line[pos+1:].strip()
                    setattr(self, f'_{k}', v)
                else:
                    pos = line.find(':')
                    if pos > 0:
                        k = line[:pos].strip().lower()
                        v = line[pos+1:].strip()
                        setattr(self, f'_{k}', v)
        deps = set()
        if hasattr(self, '_requires'):
            for req in self._requires.split():
                deps.add(Package(req, search_paths))
        super().__init__(name, includes={self._includedir}, dependencies=deps, all=False)
        
    @property
    def cxx_flags(self):
        tmp = set(self._cflags.split())
        for dep in self.cxx_dependencies:
            tmp.update(dep.cxx_flags)
        return tmp
    
    @property
    def libs(self):
        tmp = set(self._libs.split())
        for dep in self.cxx_dependencies:
            tmp.update(dep.libs)
        return tmp
    
    @property
    def up_to_date(self):
        return True

    def __getattribute__(self, name: str):
        value = super().__getattribute__(name)
        if type(value) == str:
            while True:
                m = re.search(r'\${(\w+)}', value)
                if m:
                    var = m.group(1)
                    value = value.replace(f'${{{var}}}', getattr(self, f'_{var}'))
                else:
                    break
        return value
