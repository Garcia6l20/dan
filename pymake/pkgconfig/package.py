from copy import deepcopy
import functools
import jinja2
from pymake.core import aiofiles, asyncio
from pymake.core.pathlib import Path
import re
import importlib.util

from pymake.core.find import find_file, library_paths_lookup
from pymake.core.settings import InstallMode, InstallSettings
from pymake.core.utils import unique
from pymake.cxx.targets import CXXTarget, Library
from pymake.logging import Logging


class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def find_pkg_config(name, paths=list()) -> Path:
    return find_file(fr'.*{name}\.pc', ['$PKG_CONFIG_PATH', *paths, *library_paths_lookup])


def has_package(name,  paths=list()):
    return find_pkg_config(name,  paths) is not None


class Data:
    def __init__(self) -> None:
        self._items = dict()

    __split_expr = re.compile(r'(.+?)[:=](.+)')

    async def load(self, config):
        async with aiofiles.open(config) as f:
            lines = [l for l in [l.strip().removesuffix('\n')
                                 for l in await f.readlines()] if len(l)]
            for line in lines:
                m = Data.__split_expr.match(line)
                if m:
                    k = m.group(1).lower()
                    v = m.group(2)
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


class AbstractPackage:

    @property
    def found(self) -> bool:
        """Check if the package has been found or not

        :retun: True if package has been found
        """
        ...


class UnresolvedPackage(Logging):
    def __init__(self, name: str):
        self.name = name
        super().__init__(name)

    @property
    def found(self):
        return False

    def __skipped_method_call(self, name, *args, **kwargs):
        self.debug('call to %s skipped (unresolved)', name)

    def __getattr__(self, name):
        return functools.partial(self.__skipped_method_call, name)


class Package(CXXTarget):
    all: dict[str, 'Package'] = dict()

    def __init__(self, name, search_paths: list[str] = list(), config_path: Path = None) -> None:
        self.output = None
        self.config_path = config_path or find_pkg_config(name, search_paths)
        self.search_paths = search_paths
        self.data = Data()
        if not self.config_path:
            raise MissingPackage(name)
        self.search_paths.insert(0, self.config_path.parent)
        super().__init__(name, all=False)
        self.all[name] = self

        pymake_plugin = self.config_path.parent.parent / \
            'pymake' / f'{self.name}.py'
        if pymake_plugin.exists():
            spec = importlib.util.spec_from_file_location(
                f'{self.name}_plugin', pymake_plugin)
            module = importlib.util.module_from_spec(spec)
            setattr(module, 'self', self)
            spec.loader.exec_module(module)

    @property
    def found(self):
        return True

    @asyncio.cached
    async def preload(self):
        await self.data.load(self.config_path)
        deps = set()
        requires = self.data.get('requires')
        if requires:
            for req in requires.split():
                if req in self.all:
                    deps.add(self.all[req])
                else:
                    deps.add(Package(req, self.search_paths))
        self.includes.public.append(self.data.get('includedir'))
        self.dependencies.update(deps)

        await super().preload()

    @asyncio.cached
    async def initialize(self):
        # a package is initialized in preload
        await self.preload()

    @property
    def cxx_flags(self):
        tmp: list[str] = self.data.get('cflags').split()
        for dep in self.cxx_dependencies:
            tmp.extend(dep.cxx_flags)
        return unique(tmp)

    @property
    def package_dependencies(self):
        return [pkg for pkg in self.dependencies if isinstance(pkg, Package)]

    @property
    def libs(self):
        tmp = list()
        for pkg in self.package_dependencies:
            tmp.extend(pkg.libs)
        libs = self.data.get('libs')
        if libs:
            tmp.extend(libs.split())
        return unique(tmp)

    @asyncio.cached
    async def install(self, settings: InstallSettings, mode: InstallMode) -> list[Path]:
        settings = deepcopy(settings)
        settings.create_pkg_config = False
        return await super().install(settings, mode)

    @property
    def up_to_date(self):
        return True

    @property
    def modification_time(self):
        return self.config_path.modification_time

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
    from pymake.cxx import target_toolchain
    dest = settings.libraries_destination / 'pkgconfig' / f'{lib.name}.pc'
    lib.info(f'creating pkgconfig: {dest}')
    requires = [dep for dep in lib.dependencies if isinstance(dep, Package)]
    libs = target_toolchain.make_link_options(
        [Path(f'${{libdir}}/{lib.name}')]) if not lib.interface else []
    libs.extend(lib.link_libraries.public)
    libs.extend(lib.link_options.public)
    cflags = lib.compile_definitions.public
    cflags.extend(target_toolchain.make_include_options(['${includedir}']))
    data = _get_jinja_env()\
        .get_template('pkg.pc.jinja2')\
        .render({
            'lib': lib,
            'libs': libs,
            'cflags': cflags,
            'settings': settings,
            'prefix': Path(settings.destination).absolute(),
            'requires': requires
        })
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, 'w') as f:
        await f.write(data)
    return dest
