from contextlib import contextmanager
from functools import cached_property
import importlib.util
import os
import sys
from pymake.core import aiofiles, asyncio

from pymake.core.pathlib import Path
from pymake.core.cache import Cache
from pymake.core.settings import InstallMode, InstallSettings

from pymake.core.target import Options, Target
from pymake.core.test import Test, AsyncExecutable
from pymake.logging import Logging
from pymake.pkgconfig.package import AbstractPackage, Package, UnresolvedPackage


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


def requires(*names) -> list[AbstractPackage]:
    ''' Requirement lookup

    1. Searches for a target exported by a previously included makefile
    2. Searches for pkg-config library
    3. Raises LoadRequest exception, that should trig a package lookup/installation,
        then reload the makefile requiring the package
        (that should be resolved by its locally installed pkg-config)

    :param names: One (or more) requirement(s).
    :return: The list of found targets.
    :raises LoadRequest: Unfound requirements to resolve.
    '''
    global context
    res = list()
    for name in names:
        pkg = UnresolvedPackage(name)
        for t in context.exported_targets:
            if t.name == name:
                pkg = t
                break
        else:
            for t in Package.all.values():
                if t.name == name:
                    pkg = t
                    break
            else:
                try:
                    pkg = Package(name, search_paths=[
                        context.current.build_path / 'pkgs'])
                except:
                    pass

        res.append(pkg)

    return res


class MakeFile(sys.__class__):

    def _setup(self,
               name: str,
               source_path: Path,
               build_path: Path,
               requirements: 'MakeFile' = None) -> None:
        self.name = name
        self.description = None
        self.version = None
        self.source_path = source_path
        self.build_path = build_path
        self.requirements = requirements
        self.parent: MakeFile = self.parent if hasattr(
            self, 'parent') else None
        self.targets: set[Target] = set()
        self.__exports: list[Target] = list()
        self.__installs: list[Target] = list()
        self.__cache: Cache = None
        self.__tests: list[Test] = list()
        self.children: list[MakeFile] = list()
        if self.name != 'requirements' and self.parent:
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

    def install(self, *targets: Target):
        self.__installs.extend(targets)

    def find(self, name) -> Target:
        """Find a target.

        Args:
            name (str): The target name to find.

        Returns:
            Target: The found target or None.
        """
        for t in self.exported_targets:
            if t.name == name:
                return t
        for c in self.children:
            t = c.find(name)
            if t:
                return t

    def add_test(self, executable: AsyncExecutable, args: list[str] = list(), name: str = None, file: Path | str = None, lineno: int = None):
        self.__tests.append(
            Test(self, executable, name=name, args=args, file=file, lineno=lineno))

    @property
    def tests(self):
        tests = self.__tests
        for c in self.children:
            tests.extend(c.tests)
        return tests

    @property
    def exported_targets(self) -> list[Target]:
        return self.__exports

    @property
    def installed_targets(self):
        targets = self.__installs
        for c in self.children:
            targets.extend(c.installed_targets)
        return targets

    @property
    def all_targets(self):
        targets = self.targets
        for c in self.children:
            targets.update(c.all_targets)
        return targets

    @property
    def default_targets(self):
        targets = {t for t in self.targets if t.default == True}
        for c in self.children:
            targets.update(c.default_targets)
        return targets


class Context(Logging):
    def __init__(self) -> None:
        self.__root: MakeFile = None
        self.__current: MakeFile = None
        self.__all_makefiles: set[MakeFile] = set()
        super().__init__('context')

    @property
    def root(self):
        return self.__root

    @property
    def current(self):
        return self.__current

    @property
    def all_makefiles(self) -> set[MakeFile]:
        return self.__all_makefiles

    @property
    def all_targets(self) -> set[Target]:
        return self.root.all_targets

    @property
    def exported_targets(self) -> set[Target]:
        return self.root.exported_targets

    @property
    def default_targets(self) -> set[Target]:
        return self.root.default_targets

    @property
    def installed_targets(self) -> set[Target]:
        return self.root.installed_targets

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
    """Reset whole context

    Mainly used for test purpose
    """
    global context
    for m in context.all_makefiles:
        del m
    del context
    context = Context()


def _init_makefile(module, name: str = 'root', build_path: Path = None, requirements: MakeFile = None):
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
        build_path,
        requirements)


def load_makefile(module_path: Path, name: str = None, build_path: Path = None) -> MakeFile:
    name = name or module_path.stem
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
        lookups = [
            os.path.join(name, 'makefile.py'),
            f'{name}.py',
        ]
        for lookup in lookups:
            module_path = context.current.source_path / lookup
            if module_path.exists():
                spec = importlib.util.spec_from_file_location(
                    f'{context.current.name}.{name}', module_path)
                break
        else:
            raise RuntimeError(
                f'Cannot find anything to include for "{name}" (looked for: {", ".join(lookups)})')
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path)

    requirements_file = module_path.with_stem('requirements')
    if module_path.stem == 'makefile' and requirements_file.exists():
        context.current.requirements = load_makefile(
            requirements_file, name='requirements')

    exports = list()
    try:
        spec.loader.exec_module(module)
        exports = context.exported_targets
    except LoadRequest as missing:
        context.missing.append(missing)
    except TargetNotFound as err:
        if len(context.missing) == 0:
            raise err
    context.up()
    return exports


def include(*names: str | Path) -> list[Target]:
    """Include one (or more) subdirectory (or named makefile).

    :param names: One (or more) subdirectory or makefile to include.
    :return: The list of targets exported by the included targets.
    """
    result = list()
    for name in names:
        result.extend(include_makefile(name))
    return result
