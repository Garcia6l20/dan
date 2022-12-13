import importlib.util
import sys

from pathlib import Path

from pymake.core.target import Target


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

    def export(self, *targets: Target):
        for target in targets:
            self.__exports.add(target)

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
    def all(self) -> set[Target]:
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


def include(name: str | Path, build_path: Path = None) -> set[Target]:
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
