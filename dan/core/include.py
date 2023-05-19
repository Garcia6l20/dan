import importlib.util
import os

from dan.core.asyncio import sync_wait
from dan.core.makefile import MakeFile
from dan.core.pathlib import Path
from dan.core.requirements import load_requirements
from dan.core.target import Target
from dan.logging import Logging
from dan.pkgconfig.package import parse_requirement


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


def _init_makefile(module, name: str = 'root', build_path: Path = None, requirements: MakeFile = None, parent: MakeFile = None):
    global context
    source_path = Path(module.__file__).parent
    if parent is None and context.current is not None:
        parent = context.current

    if build_path is None:
        assert parent is not None
        build_path = build_path or parent.build_path / name

    module.__class__ = MakeFile
    context.current = module
    module._setup(
        name,
        source_path,
        build_path,
        requirements,
        parent)

_imported_makefiles: dict[Path, MakeFile] = dict()

def load_makefile(module_path: Path, name: str = None, module_name: str = None, build_path: Path = None, requirements: MakeFile = None, parent: MakeFile = None) -> MakeFile:
    name = name or module_path.stem
    module_name = module_name or name
    if module_path in _imported_makefiles:
        return _imported_makefiles[module_path]
    spec = importlib.util.spec_from_file_location(
        module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    _imported_makefiles[module_path] = module
    _init_makefile(module, name, build_path, requirements, parent)
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
        module_path: Path = name / 'dan-build.py'
        spec = importlib.util.spec_from_file_location(
            'root', module_path)
        name = 'root'
    else:
        lookups = [
            os.path.join(name, 'dan-build.py'),
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
        
    if module_path in _imported_makefiles:
        return _imported_makefiles[module_path]

    module = importlib.util.module_from_spec(spec)
    _imported_makefiles[module_path] = module
    _init_makefile(module, name, build_path)

    requirements_file = module_path.with_stem('dan-requires')
    if module_path.stem == 'dan-build' and requirements_file.exists():
        context.current.requirements = load_makefile(
            requirements_file, name='dan-requires', module_name=f'{name}.requirements')

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
