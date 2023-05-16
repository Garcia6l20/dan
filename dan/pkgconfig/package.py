from copy import deepcopy
import jinja2
from dan.core import aiofiles, asyncio
from dan.core.pathlib import Path
import re
import importlib.util

from dan.core.find import find_file, find_files, library_paths_lookup
from dan.core.requirements import RequiredPackage, parse_requirement
from dan.core.runners import cmdline2list
from dan.core.settings import InstallMode, InstallSettings
from dan.core.utils import unique
from dan.core.version import Version, VersionSpec
from dan.cxx.targets import CXXTarget, Library


class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def find_pkg_config(name, paths=list()) -> Path:
    return find_file(fr'.*{name}\.pc$', ['$PKG_CONFIG_PATH', *paths, *library_paths_lookup])

def find_pkg_configs(name, paths=list()) -> Path:
    return find_files(fr'.*{name}\.pc$', ['$PKG_CONFIG_PATH', *paths, *library_paths_lookup])


def has_package(name,  paths=list()):
    return find_pkg_config(name,  paths) is not None



class Data:
    def __init__(self, path) -> None:
        self._path = Path(path)
        self._items = dict()
        with open(self._path) as f:
            lines = [l for l in [l.strip().removesuffix('\n')
                                 for l in f.readlines()] if len(l)]
            for line in lines:
                m = Data.__split_expr.match(line)
                if m:
                    k = m.group(1).lower()
                    v = m.group(2)
                    self._items[k] = v
        self.__requires = None
        self.__version = None

    __split_expr = re.compile(r'(.+?)[:=](.+)')

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
    
    @property
    def path(self) -> Path:
        return self._path
    
    @property
    def requires(self) -> list[RequiredPackage]:
        if self.__requires is None:
            self.__requires = list()
            reqs = self.get('requires')
            if reqs is not None:
                reqs = reqs.strip()
                # conan generates invalid requires clause
                # it should be 'comma separated values but it is not'
                #  eg.: 'boost-headers boost-_cmake'
                if any([c in reqs for c in ',=']):
                    # the right way
                    for req in reqs.split(','):
                        req = parse_requirement(req)
                        self.__requires.append(req)
                else:
                    # conan's way
                    for req in reqs.split(' '):
                        req = parse_requirement(req)
                        self.__requires.append(req)
        return self.__requires
    
    @property
    def version(self) -> Version:
        if self.__version is None:
            v = self.get('version')
            if v:
                self.__version = Version(v)
        return self.__version


class Package(CXXTarget, internal=True):
    all: dict[str, 'Package'] = dict()

    default = False

    def __init__(self, name, search_paths: list[str] = list(), config_path: Path = None, data: Data = None, **kwargs) -> None:
        if data is not None:
            self.config_path = data.path
            self.data = data
        else:
            self.config_path = config_path or find_pkg_config(name, search_paths)
            self.data: Data = None
        self.search_paths = search_paths
        if not self.config_path:
            raise MissingPackage(name)
        self.search_paths.insert(0, self.config_path.parent)
        self.all[name] = self

        super().__init__(name, **kwargs)

        dan_plugin = self.config_path.parent.parent / \
            'dan' / f'{self.name}.py'
        if dan_plugin.exists():
            spec = importlib.util.spec_from_file_location(
                f'{self.name}_plugin', dan_plugin)
            module = importlib.util.module_from_spec(spec)
            setattr(module, 'self', self)
            spec.loader.exec_module(module)
        self.__cflags = None
        self.__libs = None
        if not data:
            self.data = Data(self.config_path)


        self.version = self.data.version

    @property
    def modification_time(self):
        return 0.0

    @property
    def found(self):
        return True

    async def __initialize__(self):
        deps = set()
        reqs = self.data.requires
        if reqs:
            async with asyncio.TaskGroup(f'resolving {self.name}\'s requirements') as group:
                for req in reqs:
                    if req.name in self.all and req.is_compatible(self.all[req.name]):
                        dep = self.all[req.name]
                    else:
                        dep = find_package(req.name, req.version_spec, search_paths=self.search_paths, makefile=self.makefile)
                    group.create_task(dep.initialize())
                    deps.add(dep)
        self.includes.public.append(self.data.get('includedir'))
        self.dependencies.update(deps)

    @property
    def cxx_flags(self):
        if self.__cflags is None:
            from dan.cxx import target_toolchain
            cflags = self.data.get('cflags')
            if cflags is not None:
                cflags = cmdline2list(cflags)
                cflags = target_toolchain.from_unix_flags(cflags)
            else:
                cflags = list()
            for dep in self.cxx_dependencies:
                cflags.extend(dep.cxx_flags)
            self.__cflags = unique(cflags)
        return self.__cflags

    @property
    def package_dependencies(self):
        return [pkg for pkg in self.dependencies if isinstance(pkg, Package)]

    @property
    def libs(self):
        if self.__libs is None:
            from dan.cxx import target_toolchain
            tmp = list()
            libs = self.data.get('libs')
            if libs is not None:
                libs = cmdline2list(libs)
                libs = target_toolchain.from_unix_flags(libs)
                tmp.extend(libs)
            for pkg in self.package_dependencies:
                tmp.extend(pkg.libs)
            self.__libs = unique(tmp)
        return self.__libs

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
        value = self.data.get(name) if self.data is not None else None
        if value is None:
            raise AttributeError(name)
        return value


_jinja_env: jinja2.Environment = None


def find_package(name, spec: VersionSpec = None, search_paths: list = None, makefile = None):
    if makefile is None:
        from dan.core.include import context
        makefile = context.current
    search_paths = search_paths or makefile.pkgs_path
    for config in find_pkg_configs(name, search_paths):
        if spec is not None:
            data = Data(config)
            if spec.is_compatible(data.version):
                return Package(name, data=data, makefile=makefile)
        else:
            return Package(name, config_path=config, makefile=makefile)


def _get_jinja_env():
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = jinja2.Environment(
            loader=jinja2.PackageLoader('dan.pkgconfig'))
    return _jinja_env


async def create_pkg_config(lib: Library, settings: InstallSettings) -> Path:
    from dan.cxx import target_toolchain
    dest = settings.libraries_destination / 'pkgconfig' / f'{lib.name}.pc'
    lib.info(f'creating pkgconfig: {dest}')

    requires = list()
    for req in lib.requires:
        if req.version_spec:
            requires.append(f'{req.name} {req.version_spec.op} {req.version_spec.version}')
        else:
            requires.append(req.name)

    libs = target_toolchain.make_link_options(
        [Path(f'${{libdir}}/{lib.name}')]) if not lib.interface else []
    libs.extend(lib.link_libraries.public)
    libs.extend(lib.link_options.public)
    libs = target_toolchain.to_unix_flags(libs)

    cflags = lib.compile_definitions.public
    cflags.extend(target_toolchain.make_include_options(['${includedir}']))
    cflags = target_toolchain.to_unix_flags(cflags)

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
