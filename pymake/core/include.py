from functools import cached_property
import importlib.util
import inspect
import os
import sys

from pymake.core.pathlib import Path
from pymake.core.cache import Cache

from pymake.core.target import Options, Target
from pymake.core.test import Test, AsyncExecutable
from pymake.logging import Logging
from pymake.pkgconfig.package import AbstractPackage, MissingPackage, Package, UnresolvedPackage


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
        for t in context.root.all_targets:
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
                        context.current.build_path / 'pkgs'], makefile=context.current)
                except MissingPackage:
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
        self.__requirements = requirements
        self.parent: MakeFile = self.parent if hasattr(
            self, 'parent') else None
        self.__cache: Cache = None
        self.children: list[MakeFile] = list()
        if self.name != 'requirements' and self.parent:
            self.parent.children.append(self)
        self.options = Options(self)
        self.__targets: set[Target] = set()
        self.__tests: set[Test] = set()

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

    def register(self, cls: type[Target | Test]):
        if issubclass(cls, Target):
            self.__targets.add(cls)
        if issubclass(cls, Test):
            self.__tests.add(cls)
        cls.makefile = self
        return cls
    
    def __get_classes(self, derived_from: type|tuple[type, ...] = None):
        def __is_own_class(cls):
            return inspect.isclass(cls) and self.fullname.endswith(cls.__module__) and (derived_from is None or issubclass(cls, derived_from))
        return inspect.getmembers(self, __is_own_class)
    
    def _load(self):
        for name, target in self.__get_classes((Target, Test)):
            self.register(target)

    def find(self, name) -> Target:
        """Find a target.

        Args:
            name (str): The target name to find.

        Returns:
            Target: The found target or None.
        """
        for t in self.targets:
            if t.name == name:
                return t
        for c in self.children:
            t = c.find(name)
            if t:
                return t

    @property
    def requirements(self):
        if self.__requirements is not None:
            return self.__requirements
        elif self.parent is not None:
            return self.parent.requirements

    @requirements.setter
    def requirements(self, value: 'MakeFile'):
        self.__requirements = value

    @property
    def targets(self):
        return self.__targets

    @property
    def all_targets(self) -> list[type[Target]]:
        targets = self.targets
        for c in self.children:
            targets.update(c.all_targets)
        return targets

    @property
    def tests(self):
        return self.__tests

    @property
    def all_tests(self):
        tests = self.tests
        for c in self.children:
            tests.update(c.all_tests)
        return tests

    @property
    def executables(self):
        from pymake.cxx import Executable
        return {target for target in self.targets if issubclass(target, Executable)}

    @property
    def all_executables(self):
        executables = self.executables
        for c in self.children:
            executables.update(c.all_executables)
        return executables

    @property
    def installed(self):
        return {target for target in self.targets if target.installed == True}

    @property
    def all_installed(self):
        return {target for target in self.all_targets if target.installed == True}

    @property
    def default(self):
        return {target for target in self.targets if target.default == True}

    @property
    def all_default(self):
        return {target for target in self.all_targets if target.default == True}


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


def load_makefile(module_path: Path, name: str = None, module_name: str = None, build_path: Path = None) -> MakeFile:
    name = name or module_path.stem
    module_name = module_name or name
    spec = importlib.util.spec_from_file_location(
        module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path)
    spec.loader.exec_module(module)
    module._load()
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
            requirements_file, name='requirements', module_name=f'{name}.requirements')

    try:
        spec.loader.exec_module(module)
        module._load()
    except LoadRequest as missing:
        context.missing.append(missing)
    except TargetNotFound as err:
        if len(context.missing) == 0:
            raise err
    context.up()


def include(*names: str | Path) -> list[Target]:
    """Include one (or more) subdirectory (or named makefile).

    :param names: One (or more) subdirectory or makefile to include.
    :return: The list of targets exported by the included targets.
    """
    for name in names:
        include_makefile(name)
