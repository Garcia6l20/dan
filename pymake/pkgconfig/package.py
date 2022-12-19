import jinja2
from pymake.core import aiofiles, asyncio
from pymake.core.pathlib import Path
import re

from pymake.core.find import find_file, library_paths_lookup
from pymake.core.settings import InstallSettings
from pymake.core.utils import unique
from pymake.cxx.targets import Library


class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def find_pkg_config(name, paths=list()) -> Path:
    return find_file(fr'.*{name}\.pc', ['$PKG_CONFIG_PATH', *paths, *library_paths_lookup])


class Data:
    def __init__(self) -> None:
        self._items = dict()

    async def load(self, config):
        async with aiofiles.open(config) as f:
            lines = [l for l in [l.strip().removesuffix('\n')
                                 for l in await f.readlines()] if len(l)]
            for line in lines:
                pos = line.find('=')
                if pos > 0:
                    k = line[:pos].strip()
                    v = line[pos+1:].strip()
                    self._items[k] = v
                else:
                    pos = line.find(':')
                    if pos > 0:
                        k = line[:pos].strip().lower()
                        v = line[pos+1:].strip()
                        self._items[k] = v

    def get(self, name: str, default=None):
        if not name in self._items:
            return default
        value = self._items[name]
        if type(value) == str:
            while True:
                m = re.search(r'\${(\w+)}', value)
                if m:
                    var = m.group(1)
                    value = value.replace(
                        f'${{{var}}}', self.get(var))
                else:
                    break
        return value


class Package(Library):
    __all: dict[str, 'Package'] = dict()

    def __init__(self, name, search_paths: list[str] = list(), config_path: Path = None) -> None:
        self.output = None
        self.config_path = config_path or find_pkg_config(name, search_paths)
        self.search_paths = search_paths
        self.data = Data()
        if not self.config_path:
            raise MissingPackage(name)
        self.search_paths.insert(0, self.config_path.parent)
        super().__init__(name, all=False)
        self.__all[name] = self

    @asyncio.once_method
    async def preload(self):
        await self.data.load(self.config_path)
        deps = set()
        requires = self.data.get('requires')
        if requires:
            for req in requires.split():
                if req in self.__all:
                    deps.add(self.__all[req])
                else:
                    deps.add(Package(req, self.search_paths))
        self.includes.public.append(self.data.get('includedir'))
        self.dependencies.update(deps)
        
        await super().preload(recursive_once=True)

    @property
    def cxx_flags(self):
        tmp: list[str] = self.data.get('cflags').split()
        for dep in self.cxx_dependencies:
            tmp.extend(dep.cxx_flags)
        return unique(tmp)

    @property
    def libs(self):
        tmp = list(self.data.get('libs').split())
        for dep in self.cxx_dependencies:
            tmp.extend(dep.libs)
        return unique(tmp)

    @property
    def up_to_date(self):
        return True

    async def __call__(self):
        pass

    def __getattr__(self, name):
        value = self.data.get(name)
        if value is None:
            raise AttributeError(name)
        return value


_jinja_env: jinja2.Environment = None


def find_package(name):
    from pymake.core.include import context
    return Package(name, search_paths=[context.root.build_path / 'pkgs'])


def _get_jinja_env():
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = jinja2.Environment(
            loader=jinja2.PackageLoader('pymake.pkgconfig'))
    return _jinja_env


async def create_pkg_config(lib: Library, settings: InstallSettings) -> Path:
    dest = settings.libraries_destination / 'pkgconfig' / f'{lib.name}.pc'
    lib.info(f'creating pkgconfig: {dest}')
    data = _get_jinja_env()\
        .get_template('pkg.pc.jinja2')\
        .render({'lib': lib, 'settings': settings, 'prefix': Path(settings.destination).absolute()})
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, 'w') as f:
        await f.write(data)
    return dest
