import importlib.util
import os
import re
from pymake.core.asyncio import sync_wait
from pymake.core.makefile import MakeFile

from pymake.core.pathlib import Path
from pymake.core.requirements import load_requirements

from pymake.core.target import Target
from pymake.logging import Logging
from pymake.pkgconfig.package import MissingPackage, Package, RequiredPackage, parse_requirement


class TargetNotFound(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def requires(*requirements) -> list[Target]:
    ''' Requirement lookup

    1. Searches for a target exported by a previously included makefile
    2. Searches for pkg-config library

    :param names: One (or more) requirement(s).
    :return: The list of found targets.
    '''
    # return [parse_requirement(req) for req in requirements]
    global context
    requirements = [parse_requirement(req) for req in requirements]
    sync_wait(load_requirements(requirements, makefile=context.current, install=False))
    return requirements


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


def load_makefile(module_path: Path, name: str = None, module_name: str = None, build_path: Path = None, requirements: MakeFile = None) -> MakeFile:
    name = name or module_path.stem
    module_name = module_name or name
    spec = importlib.util.spec_from_file_location(
        module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path, requirements)
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
            requirements_file, name='requirements', module_name=f'{name}.requirements')

    try:
        spec.loader.exec_module(module)
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
