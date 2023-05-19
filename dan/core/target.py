from functools import cached_property
import functools
from dan.core.register import MakefileRegister
from dan.core.pathlib import Path
from typing import Any, Callable, Iterable, Union, TypeAlias
import inspect

from dan.core import asyncio, aiofiles, utils
from dan.core.requirements import load_requirements
from dan.core.settings import InstallMode, InstallSettings, safe_load
from dan.core.version import Version
from dan.logging import Logging


class Dependencies:

    def __init__(self, parent: 'Target', deps: Iterable = list()):
        super().__init__()
        self.parent = parent
        self._content = list()
        for dep in deps:
            self.add(dep)

    @property
    def makefile(self):
        return self.parent.makefile

    def add(self, dependency):
        if dependency in self._content:
            return
        from dan.pkgconfig.package import RequiredPackage
        match dependency:
            case Target() | FileDependency():
                self._content.append(dependency)
            case type():
                assert issubclass(dependency, Target)
                self._content.append(self.makefile.find(dependency))
            case str():
                from dan.pkgconfig.package import Package
                for pkg in Package.all.values():
                    if pkg.name == dependency:
                        self.append(pkg)
                        break
                else:
                    if Path(self.parent.source_path / dependency).exists():
                        self._content.append(FileDependency(
                            self.parent.source_path / dependency))
                    else:
                        from dan.pkgconfig.package import parse_requirement
                        self._content.append(parse_requirement(dependency))
            case Path():
                dependency = FileDependency(
                    self.parent.source_path / dependency)
                self._content.append(dependency)
            case RequiredPackage():
                self._content.append(dependency)
            case _:
                raise RuntimeError(
                    f'Unhandled dependency {dependency} ({type(dependency)})')

    def update(self, dependencies):
        for dep in dependencies:
            self.add(dep)

    def __getattr__(self, attr):
        for item in self._content:
            if item.name == attr:
                return item

    def __iter__(self):
        return self._content.__iter__()

    @property
    def up_to_date(self):
        for item in self:
            if not item.up_to_date:
                return False
        return True

    @property
    def modification_time(self):
        t = 0.0
        for item in self:
            mt = item.modification_time
            if mt and mt > t:
                t = mt
        return t


TargetDependencyLike: TypeAlias = Union[list['Target'], 'Target']


PathImpl = type(Path())


class FileDependency(PathImpl):
    up_to_date = True

    def __init__(self, *args, **kwargs):
        super(PathImpl, self).__init__()

    @property
    def modification_time(self):
        return self.stat().st_mtime


class Option:
    def __init__(self, parent: 'Options', fullname: str, default, help: str = None) -> None:
        self.fullname = fullname
        self.name = fullname.split('.')[-1]
        self.__parent = parent
        self.__cache = parent._cache
        self.__default = default
        self.__value = self.__cache.get(self.name, default)
        self.__value_type = type(default)
        self.__help = help if help is not None else 'No description.'

    def reset(self):
        self.value = self.__default

    @property
    def parent(self):
        return self.__parent

    @property
    def cache(self):
        return self.__cache

    @property
    def type(self):
        return self.__value_type

    @property
    def default(self):
        return self.__default

    @property
    def help(self):
        return self.__help

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):
        value = safe_load(self.fullname, value, self.__value_type)
        if self.__value != value:
            self.__value = value
            self.__cache[self.name] = value


class Options:
    def __init__(self, parent: 'Target', default: dict[str, Any] = dict()) -> None:
        self.__parent = parent
        cache = parent.cache
        if isinstance(parent.cache, dict):
            if not parent.name in cache:
                cache[parent.name] = dict()
            cache = cache[parent.name]
        else:
            cache = parent.cache.data
        if not 'options' in cache:
            cache['options'] = dict()
        self._cache = cache['options']
        self.__items: set[Option] = set()
        self.update(default)

    def add(self, name: str, default_value, help=None):
        opt = Option(self, f'{self.__parent.fullname}.{name}',
                     default_value, help=help)
        self.__items.add(opt)
        return opt

    def get(self, name: str):
        for o in self.__items:
            if name in {o.name, o.fullname}:
                return o

    def update(self, options: dict):
        for k, v in options.items():
            help = None
            match v:
                case dict():
                    help = v['help']
                    v = v['default']
                case tuple() | list() | set():
                    help = v[1]
                    v = v[0]
                case _:
                    pass
            if self[k]:
                self[k] = v
            else:
                self.add(k, v, help)

    def items(self):
        for o in self.__items:
            yield o.name, o.value

    def __getattr__(self, name):
        opt = self.get(name)
        if opt:
            return opt.value

    def __getitem__(self, name):
        opt = self.get(name)
        if opt:
            return opt.value

    def __iter__(self):
        return iter(self.__items)


class Target(Logging, MakefileRegister, internal=True):
    name: str = None
    fullname: str = None
    description: str = None,
    default: bool = True
    installed: bool = False
    output: Path = None
    options: dict[str, Any] = dict()

    dependencies: set[TargetDependencyLike] = set()
    preload_dependencies: set[TargetDependencyLike] = set()

    def __init__(self,
                 name: str = None,
                 parent: 'Target' = None,
                 version: str = None,
                 default: bool = None,
                 makefile=None) -> None:
        
        self.parent = parent
        self.__cache: dict = None

        if name is not None:
            self.name = name

        if self.name is None:
            self.name = self.__class__.__name__

        if default is not None:
            self.default = default

        if parent is not None:
            self.makefile = parent.makefile
            self.fullname = f'{parent.fullname}.{self.name}'

        if makefile:
            self.makefile = makefile

        if self.makefile is None:
            raise RuntimeError('Makefile not resolved')


        if self.fullname is None:
            self.fullname = f'{self.makefile.fullname}.{self.name}'

        self.options = Options(self, self.options)

        if version is not None:
            self._version = version

        if not hasattr(self, '_version'):
            self._version = self.makefile.version

        if self.description is None:
            self.description = self.makefile.description

        self.other_generated_files: set[Path] = set()
        self.dependencies = Dependencies(self, self.dependencies)
        self.preload_dependencies = Dependencies(
            self, self.preload_dependencies)

        super().__init__(self.fullname)

        self._output: Path = None

        if type(self).output != Target.output:
            # hack class-defined output
            #   transform it to classproperty for build_path resolution
            output = self.output
            type(self).output = utils.classproperty(lambda: self.build_path / output)

    
    @property
    def output(self):
        if self._output is None:
            return None
        return self.build_path / self._output
    
    @property
    def version(self):
        version = self._version
        if isinstance(version, Option):
            version = version.value
        if isinstance(version, str):
            version = Version(version)
        return version

    @version.setter
    def version(self, value):
        self._version = value

    @output.setter
    def output(self, path):
        path = Path(path)
        if path.is_absolute() and self.build_path in path.parents:
            raise RuntimeError(f'output must not be an absolute path within build directory')
        self._output = path

    @property
    def is_requirement(self) -> bool:
        return self.makefile.name.endswith('requirements')

    @property
    def source_path(self) -> Path:
        return self.makefile.source_path

    @property
    def build_path(self) -> Path:
        return self.makefile.build_path
    
    @property
    def requires(self):
        from dan.pkgconfig.package import RequiredPackage
        return [dep for dep in self.dependencies if isinstance(dep, RequiredPackage)]

    @cached_property
    def fullname(self) -> str:
        return f'{self.makefile.fullname}.{self.name}'

    @property
    def cache(self) -> dict:
        if not self.__cache:
            name = self.fullname.removeprefix(self.makefile.fullname + '.')
            if not name in self.makefile.cache.data:
                self.makefile.cache.data[name] = dict()
            self.__cache = self.makefile.cache.data[name]
        return self.__cache

    async def __load_unresolved_dependencies(self):
        if len(self.requires) > 0:
            self.dependencies.update(await load_requirements(self.requires, makefile=self.makefile, logger=self))

    @asyncio.cached
    async def preload(self):
        self.debug('preloading...')

        async with asyncio.TaskGroup(f'building {self.name}\'s preload dependencies') as group:
            group.create_task(self.__load_unresolved_dependencies())
            for dep in self.preload_dependencies:
                group.create_task(dep.build())

        async with asyncio.TaskGroup(f'preloading {self.name}\'s target dependencies') as group:
            for dep in self.target_dependencies:
                group.create_task(dep.preload())

        res = self.__preload__()
        if inspect.iscoroutine(res):
            res = await res
        return res

    @asyncio.cached
    async def initialize(self):
        await self.preload()
        self.debug('initializing...')

        if isinstance(self.version, Option):
            self.version = self.version.value

        async with asyncio.TaskGroup(f'initializing {self.name}\'s target dependencies') as group:
            for dep in self.target_dependencies:
                group.create_task(dep.initialize())

        res = self.__initialize__()
        if inspect.iscoroutine(res):
            res = await res
        return res

    @property
    def modification_time(self):
        return self.output.stat().st_mtime if self.output.exists() else 0.0

    @property
    def up_to_date(self):
        if self.output and not self.output.exists():
            return False
        elif not self.dependencies.up_to_date:
            return False
        elif self.dependencies.modification_time > self.modification_time:
            return False
        return True

    async def _build_dependencies(self):
        async with asyncio.TaskGroup(f'building {self.name}\'s target dependencies') as group:
            for dep in self.target_dependencies:
                group.create_task(dep.build())

    @asyncio.cached
    async def build(self):
        await self.initialize()

        await self._build_dependencies()

        result = self.__prebuild__()
        if inspect.iscoroutine(result):
            await result

        if self.up_to_date:
            self.info('up to date !')
            return
        elif self.output.exists():
            self.info('outdated !')

        with utils.chdir(self.build_path):
            self.info('building...')
            result = self.__build__()
            if inspect.iscoroutine(result):
                return await result
            return result

    @property
    def target_dependencies(self):
        return [t for t in {*self.dependencies, *self.preload_dependencies} if isinstance(t, Target)]

    @property
    def file_dependencies(self):
        return [t for t in self.dependencies if isinstance(t, FileDependency)]

    @asyncio.cached
    async def clean(self):
        await self.initialize()
        async with asyncio.TaskGroup(f'cleaning {self.name} outputs') as group:
            if self.output and self.output.exists():
                self.info('cleaning...')
                if self.output.is_dir():
                    group.create_task(aiofiles.rmtree(self.output))
                else:
                    group.create_task(aiofiles.os.remove(self.output))
            for f in self.other_generated_files:
                if f.exists():
                    group.create_task(aiofiles.os.remove(f))
            res = self.__clean__()
            if inspect.iscoroutine(res):
                group.create_task(res)

    @asyncio.cached
    async def install(self, settings: InstallSettings, mode: InstallMode):
        await self.build()
        installed_files = list()
        if mode == InstallMode.dev:
            if len(self.utils) > 0:
                lines = list()
                for fn in self.utils:
                    tmp = inspect.getsourcelines(fn)[0]
                    tmp[0] = f'\n\n@self.utility\n'
                    lines.extend(tmp)
                filepath = settings.libraries_destination / \
                    'dan' / f'{self.name}.py'
                filepath.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(filepath, 'w') as f:
                    await f.writelines(lines)
                    installed_files.append(filepath)
        return installed_files

    def get_dependency(self, dep: str | type, recursive=True) -> TargetDependencyLike:
        """Search for dependency"""
        if isinstance(dep, str):
            def check(d): return d.name == dep
        else:
            def check(d): return isinstance(d, dep)
        for dependency in self.dependencies:
            if check(dependency):
                return dependency
        for dependency in self.preload_dependencies:
            if check(dependency):
                return dependency
        if recursive:
            # not found... look for dependencies' dependencies
            for target in self.target_dependencies:
                dependency = target.get_dependency(dep)
                if dependency is not None:
                    return dependency

    async def __preload__(self):
        ...

    async def __initialize__(self):
        ...

    async def __prebuild__(self):
        ...

    async def __build__(self):
        ...

    async def __install__(self):
        ...

    async def __clean__(self):
        ...

    @utils.classproperty
    def utils(cls) -> list:
        utils_name = f'_{cls.__name__}_utils__'
        if not hasattr(cls, utils_name):
            setattr(cls, utils_name, list())
        return getattr(cls, utils_name)

    @classmethod
    def utility(cls, fn: Callable):
        cls.utils.append(fn)
        name = fn.__name__
        makefile = cls.get_static_makefile()
        if makefile is not None:
            inst = makefile.find(cls)
            fn = functools.partial(fn, inst)
        setattr(cls, name, fn)
        return fn
