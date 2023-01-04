from functools import cached_property
import importlib.util
import sys
from pymake.core import aiofiles, asyncio

from pymake.core.pathlib import Path
from pymake.core.cache import Cache
from pymake.core.settings import InstallMode, InstallSettings

from pymake.core.target import Options, Target
from pymake.core.test import Test, AsyncExecutable
from pymake.pkgconfig.package import Package


class TargetNotFound(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


class LoadRequest(Exception):
    def __init__(self, recipes: list[str]) -> None:
        super().__init__(f'Unloaded recipes: {", ".join(recipes)}')
        self.recipes = recipes
        self.makefile = context.current


def load(*recipes: str):
    packages_root = context.root.build_path / 'pkgs-build'
    missing_recipes = list()
    for recipe in recipes:
        if not (packages_root / recipe / 'done').exists():
            missing_recipes.append(recipe)
    if len(missing_recipes) > 0:
        raise LoadRequest(missing_recipes)


def requires(*names) -> list[Target]:
    ''' Requirement lookup
    1 - Search for existing-exported target
    2 - Look for pkg-config library
    '''
    global context
    res = list()
    for name in names:
        found = None
        for t in context.exported_targets:
            if t.name == name:
                found = t
                break

        if not found:
            for t in Package.all.values():
                if t.name == name:
                    found = t
                    break
            try:
                found = Package(name, search_paths=[context.root.build_path / 'pkgs'])
            except:
                pass


        if not found:
            raise TargetNotFound(name)
        res.append(found)
    return res


class MakeFile(sys.__class__):

    def _setup(self,
               name: str,
               source_path: Path,
               build_path: Path) -> None:
        self.name = name
        self.description = None
        self.version = None
        self.source_path = source_path
        self.build_path = build_path
        self.parent: MakeFile = self.parent if hasattr(
            self, 'parent') else None
        self.targets: set[Target] = set()
        self.__exports: list[Target] = list()
        self.__installs: list[Target] = list()
        self.__cache: Cache = None
        self.__tests: list[Test] = list()
        self.children: list[MakeFile] = list()
        if self.parent:
            self.parent.children.append(self)
        self.options = Options(self)

    @cached_property
    def fullname(self):
        return f'{self.parent.fullname}.{self.name}' if self.parent else self.name

    @property
    def cache(self) -> Cache:
        if not self.__cache:
            self.__cache = Cache(self.build_path / f'{self.name}.cache.yaml')
        return self.__cache

    def export(self, *targets: Target):
        for target in targets:
            self.__exports.append(target)
            context.exported_targets.add(target)

    def install(self, *targets: Target):
        self.__installs.extend(targets)

    @property
    def installed_targets(self):
        return self.__installs

    def add_test(self, executable: AsyncExecutable, args: list[str] = list(), name: str = None, file: Path | str = None, lineno: int = None):
        self.__tests.append(
            Test(self, executable, name=name, args=args, file=file, lineno=lineno))

    @property
    def tests(self):
        return self.__tests

    @property
    def _exported_targets(self) -> list[Target]:
        return self.__exports


class Context:
    def __init__(self) -> None:
        self.__root: MakeFile = None
        self.__current: MakeFile = None
        self.__all_makefiles: set[MakeFile] = set()
        self.__all_targets: set[Target] = set()
        self.__default_targets: set[Target] = set()
        self.__exported_targets: set[Target] = set()
        self.missing : list[LoadRequest] = list()

    async def _install_pkg(self, module_path, build_path):
        settings = InstallSettings()
        settings.destination = self.root.build_path / 'pkgs'
        pkgs_data = self.root.build_path / 'pkgs-build'
        while True:
            try:
                mf : MakeFile = load_makefile(module_path, build_path)
                tasks = list()
                for t in mf.installed_targets:
                    async def install():
                        await t.install(settings, InstallMode.dev)
                        async with aiofiles.open(build_path / 'done', 'w') as f:
                            await f.write('OK')
                    tasks.append(install())
                await asyncio.gather(*tasks)
                break
            except LoadRequest as missing:
                await self.install_missing([missing])


    async def install_missing(self, missing = None):
        tasks = list()
        settings = InstallSettings()
        settings.destination = context.root.build_path / 'pkgs'
        pkgs_data = context.root.build_path / 'pkgs-build'
        for req in (missing or self.missing):
            for recipe in req.recipes:
                module_path = req.makefile.source_path / f'{recipe}.py'
                build_path = pkgs_data / recipe
                tasks.append(self._install_pkg(module_path, build_path))
        await asyncio.gather(*tasks)

    @property
    def root(self):
        return self.__root

    @property
    def current(self):
        return self.__current

    @property
    def all_makefiles(self) -> set[MakeFile]:
        return self.__all_makefiles

    def install(self, *targets: Target):
        self.__installed_targets.update(targets)

    @property
    def all_targets(self) -> set[Target]:
        return self.__all_targets

    @property
    def exported_targets(self) -> set[Target]:
        return self.__exported_targets

    @property
    def default_targets(self) -> set[Target]:
        return self.__default_targets

    @property
    def installed_targets(self) -> set[Target]:
        targets = set()
        for m in self.all_makefiles:
            targets.update(m.installed_targets)
        return targets

    @current.setter
    def current(self, current: MakeFile):
        if self.__root is None:
            self.__root = current
            self.__current = current
        else:
            current.parent = self.__current
            self.__current = current
        self.__all_makefiles.add(current)

    def up(self):
        if self.__current != self.__root:
            self.__current = self.__current.parent

    def get(self, name, default=None):
        if hasattr(self, name):
            return getattr(self, name)
        if default is not None:
            setattr(self, name, default)
            return default

    def set(self, name, value):
        setattr(self, name, value)


context = Context()


def context_reset():
    global context
    for m in context.all_makefiles:
        del m
    del context
    context = Context()


def _init_makefile(module, name: str = 'root', build_path: Path = None):
    global context
    source_path = Path(module.__file__).parent
    if not build_path:
        assert context.current
        build_path = build_path or context.current.build_path / name
    build_path.mkdir(parents=True, exist_ok=True)

    module.__class__ = MakeFile
    context.current = module
    module._setup(
        name,
        source_path,
        build_path)


def load_makefile(module_path: Path, build_path: Path) -> MakeFile:
    name = module_path.stem
    spec = importlib.util.spec_from_file_location(
        f'{name}', module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path)
    spec.loader.exec_module(module)
    context.up()
    return module


def include_makefile(name: str | Path, build_path: Path = None) -> set[Target]:
    ''' Include a sub-directory (or a sub-makefile).
    :returns: The set of exported targets.
    '''
    global context
    if not context.root:
        assert type(name) == type(Path())
        module_path: Path = name / 'makefile.py'
        spec = importlib.util.spec_from_file_location(
            'root', module_path)
        name = 'root'
    else:
        module_path: Path = context.current.source_path / name / 'makefile.py'
        if not module_path.exists():
            module_path = context.current.source_path / f'{name}.py'
        spec = importlib.util.spec_from_file_location(
            f'{context.current.name}.{name}', module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path)
    exports = list()
    try:
        spec.loader.exec_module(module)
        exports = context.current._exported_targets
    except LoadRequest as missing:
        context.missing.append(missing)
    except TargetNotFound as err:
        if len(context.missing) == 0:
            raise err
    context.up()
    return exports


def include(*names: str | Path) -> list[Target]:
    result = list()
    for name in names:
        result.extend(include_makefile(name))
    return result
