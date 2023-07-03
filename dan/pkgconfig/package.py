from copy import deepcopy
import jinja2
from dan.core import aiofiles, asyncio
from dan.core.pathlib import Path
import re
import importlib.util

from dan.core.find import find_file, find_files, library_paths_lookup
from dan.core.pm import re_match
from dan.core.requirements import RequiredPackage, parse_requirement
from dan.core.runners import cmdline2list
from dan.core.settings import InstallMode, InstallSettings
from dan.core.utils import unique
from dan.core.version import Version, VersionSpec
from dan.cxx.targets import CXXTarget, Library
from dan.cxx.toolchain import LibraryList

import typing as t


class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def find_pkg_config(name, paths=list()) -> Path:
    return find_file(fr'.*{name}\.pc$', [*paths, '$PKG_CONFIG_PATH', *library_paths_lookup])


def find_pkg_configs(name, paths=list()) -> t.Generator[Path, None, None]:
    yield from find_files(fr'.*{name}\.pc$', [*paths, '$PKG_CONFIG_PATH', *library_paths_lookup])


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
        self.pn = name
        self.all[name] = self

        super().__init__(f'{name}-pkgconfig', **kwargs)

        dan_plugin = find_file(rf'{name}\.py', [self.config_path.parent.parent])
        if dan_plugin is not None:
            spec = importlib.util.spec_from_file_location(
                f'{name}_plugin', dan_plugin)
            module = importlib.util.module_from_spec(spec)
            setattr(module, 'self', self)
            spec.loader.exec_module(module)
        self.__cflags = None
        self.__libs = None
        self.__lib_paths = None
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
                    if dep is None:
                        raise RuntimeError(f'Unresolved requirement: {req}')
                    group.create_task(dep.initialize())
                    deps.add(dep)
        self.includes.public.append(self.data.get('includedir'))
        self.dependencies.update(deps)

    @property
    def cxx_flags(self):
        if self.__cflags is None:
            cflags = self.data.get('cflags')
            if cflags is not None:
                cflags = cmdline2list(cflags)
                cflags = self.toolchain.from_unix_flags(cflags)
            else:
                cflags = list()
            for dep in self.cxx_dependencies:
                cflags.extend(dep.cxx_flags)
            self.__cflags = unique(cflags)
        return self.__cflags

    @property
    def package_dependencies(self):
        return [pkg for pkg in self.dependencies if isinstance(pkg, Package)]

    def __init_libs(self):
        self.__libs = LibraryList()
        self.__lib_paths = set()
        libs = self.data.get('libs')
        if libs is not None:
            libs = cmdline2list(libs)
            libs = self.toolchain.from_unix_flags(libs)
            for l in libs:
                match re_match(l):
                    case r'-l(.+)' as m:
                        self.__libs.add(m[0])
                    case r'-L(.+)' as m:
                        self.__lib_paths.add(m[0])
                    case r'/LIBPATH:(.+)' as m:
                        self.__lib_paths.add(m[0])
                    case r'-Wl,-rpath,(.+)' as m:
                        self.__lib_paths.add(m[0])
                    case _:
                        self.__libs.add(l)
        for pkg in self.package_dependencies:
            self.__lib_paths.update(pkg.lib_paths)
            self.__libs.extend(pkg.libs)
        self.__lib_paths = list(sorted(self.__lib_paths))

    @property
    def lib_paths(self) -> list[str]:
        if self.__lib_paths is None:
            self.__init_libs()
        return self.__lib_paths
    
    @property
    def libs(self):
        if self.__libs is None:
            self.__init_libs()
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
    
    if name in Package.all:
        pkg = Package.all[name]
        if spec and not spec.is_compatible(pkg.version):
            raise RuntimeError(f'incompatible package {name} ({pkg.version} {spec})')
        return pkg
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
    dest = settings.data_destination / 'pkgconfig' / f'{lib.name}.pc'
    lib.info(f'creating pkgconfig: {dest}')

    requires = list()
    for dep in lib.dependencies:
        match dep:
            case RequiredPackage():
                if dep.version_spec:
                    requires.append(f'{dep.name} {dep.version_spec.op} {dep.version_spec.version}')
                else:
                    requires.append(dep.name)
            case Library():
                requires.append(dep.name)


    libs = list()
    if not lib.interface:
        libs.extend(lib.toolchain.make_libpath_options(
            [Path(f'${{libdir}}/{lib.name}')]))
        libs.extend(lib.toolchain.make_link_options(
            [Path(f'${{libdir}}/{lib.name}')]))
    libs.extend(lib.link_libraries.public)
    libs.extend(lib.link_options.public)
    libs = lib.toolchain.to_unix_flags(libs)

    cflags = lib.compile_definitions.public
    cflags.extend(lib.toolchain.make_include_options(['${includedir}']))
    cflags = lib.toolchain.to_unix_flags(cflags)

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
