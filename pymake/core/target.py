from functools import cached_property
from pymake.core.pathlib import Path
import time
from typing import Any, Callable, Iterable, Union, TypeAlias
import inspect

from pymake.core import asyncio, aiofiles, utils
from pymake.core.cache import SubCache
from pymake.core.settings import InstallMode, InstallSettings, safe_load
from pymake.core.version import Version
from pymake.logging import Logging


class Dependencies(set):

    def __init__(self, parent : 'Target', deps: Iterable = list()):
        super().__init__()
        self.parent = parent
        self.unresolved = set()
        for dep in deps:
            self.add(dep)

    
    def add(self, dependency):
        from pymake.pkgconfig.package import UnresolvedPackage
        match dependency:
            case Target() | FileDependency():
                super().add(dependency)
            case type():
                assert issubclass(dependency, Target)
                super().add(dependency())
            case str():
                from pymake.pkgconfig.package import Package
                for pkg in Package.all.values():
                    if pkg.name == dependency:
                        self.add(pkg)
                        break
                else:
                    if Path(self.parent.source_path / dependency).exists():
                        super().add(FileDependency(
                            self.parent.source_path / dependency))
                    else:
                        self.unresolved.add(UnresolvedPackage(dependency))
            case Path():
                dependency = FileDependency(self.parent.source_path / dependency)
                super().add(dependency)
            case UnresolvedPackage():
                self.unresolved.add(dependency)
            case _:
                raise RuntimeError(
                    f'Unhandled dependency {dependency} ({type(dependency)})')

    def update(self, dependencies):
        for dep in dependencies:
            self.add(dep)

    def __getattr__(self, attr):
        for item in self:
            if item.name == attr:
                return item

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
    def __init__(self, parent: 'Target', name: str, default) -> None:
        self.__parent = parent
        self.__cache = parent.cache
        self.fullname = f'{parent.name}.{name}'
        self.name = name
        self.__default = default
        if name == 'console_width':
            pass
        self.__value = getattr(self.__cache, self.fullname) if hasattr(
            self.__cache, self.fullname) else default
        self.__value_type = type(default)

    def reset(self):
        self.value = self.__default

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):
        value = safe_load(self.fullname, value, self.__value_type)
        if self.__value != value:
            self.__value = value
            setattr(self.__cache, self.fullname, value)
            setattr(self.__cache,
                    f'{self.__parent.fullname}.options.timestamp', time.time())


class Options:
    def __init__(self, parent: 'Target', default: dict[str, Any] = dict()) -> None:
        self.__parent = parent
        self.__cache = parent.cache
        self.__items: set[Option] = set()
        self.update(default)

    def add(self, name: str, default_value):
        opt = Option(self.__parent, name, default_value)
        self.__items.add(opt)
        return opt

    def get(self, name: str):
        for o in self.__items:
            if name in {o.name, o.fullname}:
                return o
            
    def update(self, options: dict):
        for k, v in options.items():
            if self[k]:
                self[k] = v
            else:
                self.add(k, v)
    
    def items(self):
        for o in self.__items:
            yield o.name, o.value

    @cached_property
    def modification_date(self):
        return self.__cache.get(f'{self.__parent.fullname}.options.timestamp', 0.0)

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


class Target(Logging):
    name: str = None
    fullname: str = None
    description: str = None,
    version: str = None
    default: bool = True
    installed: bool = False
    output: Path = None
    options: dict[str, Any] = dict()
    
    dependencies: set[TargetDependencyLike] = set()
    preload_dependencies: set[TargetDependencyLike] = set()

    makefile = None

    def __init__(self,
                 name : str = None,
                 parent: 'Target' = None,
                 version: str = None,
                 default: bool = None,
                 makefile = None) -> None:
        self.version = Version(self.version) if self.version else None
        self.parent = parent
        self.__cache: SubCache = None

        if name is not None:
            self.name = name

        if self.name is None:
            self.name = self.__class__.__name__

        if version is not None:
            self.version = version

        if default is not None:
            self.default = default

        if parent is not None:
            self.makefile = parent.makefile
            self.fullname = f'{parent.fullname}.{name}'

        if makefile is not None:
            self.makefile = makefile
        
        if self.makefile is None:
            from pymake.core.include import context
            self.makefile = context.current
        
        if self.fullname is None:
            self.fullname = f'{self.makefile.fullname}.{name}'

        self.options = Options(self, self.options)

        if self.version is None:
            self.version = self.makefile.version

        if self.description is None:
            self.description = self.makefile.description

        self.other_generated_files: set[Path] = set()
        self.dependencies = Dependencies(self, self.dependencies)
        self.preload_dependencies = Dependencies(self, self.preload_dependencies)

        super().__init__(self.fullname)

        if self.output is not None:
            self.output = Path(self.output)
            if not self.output.is_absolute():
                self.output = self.build_path / self.output

    @property
    def source_path(self) -> Path:
        return self.makefile.source_path

    @property
    def build_path(self) -> Path:
        return self.makefile.build_path
    
    @cached_property
    def fullname(self) -> str:
        return f'{self.makefile.fullname}.{self.name}'

    @property
    def cache(self) -> SubCache:
        if not self.__cache:
            self.__cache = self.makefile.cache.subcache(self.fullname)
        return self.__cache

    async def __load_unresolved_dependencies(self):
        if len(self.dependencies.unresolved) == 0:
            return
        deps_install_path = self.makefile.requirements.parent.build_path / 'pkgs'
        deps_settings = InstallSettings(deps_install_path)
        deps_installs = list()
        if self.makefile.requirements is None:
            raise RuntimeError(
                f'Unresolved dependencies maybe you should provide a requirements.py file')
        for dep in self.dependencies.unresolved:
            t = self.makefile.requirements.find(dep.name)
            if not t:
                raise RuntimeError(f'Unresolved dependency "{dep.name}"')
            deps_installs.append(t().install(deps_settings, InstallMode.dev))
        await asyncio.gather(*deps_installs)

        from pymake.pkgconfig.package import Package
        for dep in self.dependencies.unresolved:
            pkg = Package(dep.name, search_paths=[
                deps_install_path], makefile=self.makefile)
            self.dependencies.add(pkg)

    @asyncio.cached
    async def preload(self):
        self.debug('preloading...')
        # deps = self.dependencies
        # self.dependencies = Dependencies()
        # self.load_dependencies(deps)
        
        async with asyncio.TaskGroup() as group:
            group.create_task(self.__load_unresolved_dependencies())
            for dep in self.preload_dependencies:
                group.create_task(dep.build())

        async with asyncio.TaskGroup() as group:
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

        async with asyncio.TaskGroup() as group:
            for dep in self.target_dependencies:
                group.create_task(dep.initialize())

        if self.output and not self.output.is_absolute():
            self.output = self.build_path / self.output
        
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
        elif self.modification_time < self.options.modification_date:
            return False
        return True
    
    async def _build_dependencies(self):
        async with asyncio.TaskGroup() as group:
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
        async with asyncio.TaskGroup() as group:
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
                    'pymake' / f'{self.name}.py'
                filepath.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(filepath, 'w') as f:
                    await f.writelines(lines)
                    installed_files.append(filepath)
        return installed_files

    def get_dependency(self, dep:str|type, recursive=True) -> TargetDependencyLike:
        """Search for dependency"""
        if isinstance(dep, str):
            check = lambda d: d.name == dep
        else:
            check = lambda d: isinstance(d, dep)
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
        setattr(cls, fn.__name__, fn)
