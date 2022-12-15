from functools import cached_property
import importlib.util
import sys

from pymake.core.pathlib import Path
from pymake.core.cache import Cache

from pymake.core.target import Options, Target

_exported_targets: set[Target] = set()


def export(*targets: Target):
    global _exported_targets
    for target in targets:
        _exported_targets.add(target)


class TargetNotFound(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')


def requires(*names) -> set[Target]:
    global _exported_targets
    res = set()
    for name in names:
        found = None
        for t in _exported_targets:
            if t.name == name:
                found = t
                break
        if not found:
            raise TargetNotFound(name)
        res.add(found)
    return res


class MakeFile(sys.__class__):

    def _setup(self,
               name: str,
               source_path: Path,
               build_path: Path) -> None:
        self.name = name
        self.source_path = source_path
        self.build_path = build_path
        self.parent: MakeFile = self.parent if hasattr(
            self, 'parent') else None
        self.targets: set[Target] = set()
        self.__exports: set[Target] = set()
        if self.parent:
            for target in self.parent.targets:
                setattr(self, target.name, target)
        self.options = Options(self)

    @cached_property
    def cache(self) -> Cache:
        return Cache(self.build_path / f'{self.name}.cache.yaml')

    def export(self, *targets: Target):
        for target in targets:
            self.__exports.add(target)
        export(*targets)

    @property
    def _exported_targets(self) -> set[Target]:
        return self.__exports


class Context:
    def __init__(self) -> None:
        self.__root: MakeFile = None
        self.__current: MakeFile = None
        self.__all: set[MakeFile] = set()

    @property
    def root(self):
        return self.__root

    @property
    def current(self):
        return self.__current

    @property
    def all(self) -> set[MakeFile]:
        return self.__all

    @current.setter
    def current(self, current: MakeFile):
        if self.__root is None:
            self.__root = current
            self.__current = current
        else:
            current.parent = self.__current
            self.__current = current
        self.__all.add(current)

    def up(self):
        if self.__current != self.__root:
            self.__current = self.__current.parent


context = Context()


def _init_makefile(module, name: str = 'root', build_path: Path = None):
    global context
    source_path = Path(module.__file__).parent
    if context.root:
        build_path = build_path or context.current.build_path / name
        name = f'{context.current.name}.{name}'
    else:
        assert build_path
    build_path.mkdir(parents=True, exist_ok=True)

    module.__class__ = MakeFile
    context.current = module
    context.current._setup(
        name,
        source_path,
        build_path)


def _reset():
    global context
    context = Context()


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
    spec.loader.exec_module(module)
    exports = context.current._exported_targets
    context.up()
    return exports


def include(*names: str | Path) -> list[Target]:
    result = list()
    for name in names:
        result.extend(include_makefile(name))
    return result
