from functools import cached_property
import importlib.util
import sys

from pymake.core.pathlib import Path
from pymake.core.cache import Cache

from pymake.core.target import Options, Target


def export(*targets: Target):
    global context
    for target in targets:
        context.exported_targets.add(target)


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
        self.__exports: list[Target] = list()
        self.__cache: Cache = None
        if self.parent:
            for target in self.parent.targets:
                setattr(self, target.name, target)
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
        export(*targets)
    
    def install(self, *targets: Target):
        context.install(*targets)

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
        self.__installed_targets: set[Target] = set()
        self.__exported_targets: set[Target] = set()

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
        return self.__installed_targets

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


def context_reset():
    global context
    for m in context.all_makefiles:
        del m
    del context
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
