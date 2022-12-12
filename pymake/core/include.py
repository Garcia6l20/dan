import importlib.util
from pathlib import Path

from types import ModuleType

from pymake.core.target import Target


def makefile_targets(makefile_or_module):
    module = makefile_or_module.module if isinstance(makefile_or_module, MakeFile) else makefile_or_module
    targets: dict[str, Target] = dict()
    for k, v in module.__dict__.items():
        if isinstance(v, Target):
            targets[k] = v
    return targets


class MakeFile():
    def __init__(self,
                 name: str,
                 module: ModuleType,
                 parent: 'MakeFile',
                 source_path: Path,
                 build_path: Path) -> None:
        self.name = name
        self.module = module
        self.parent = parent
        self.source_path = source_path
        self.build_path = build_path
        if self.parent:
            for name, target in makefile_targets(self.parent).items():
                setattr(self.module, name, target)


# patch root makefile
root_makefile = None
current_makefile = None
makefiles = list()


def _init_makefile(module, name: str = 'root', build_path: Path = None):
    global current_makefile, root_makefile
    source_path = Path(module.__file__).parent
    if root_makefile:
        build_path = build_path or current_makefile.build_path / name
        name = f'{current_makefile.name}.{name}'
    else:
        assert build_path
    build_path.mkdir(parents=True, exist_ok=True)

    parent = current_makefile

    current_makefile = MakeFile(
        name,
        module,
        parent,
        source_path,
        build_path)
    if not root_makefile:
        root_makefile = current_makefile


def targets():
    from pymake.core.target import Target
    targets: set[Target] = set()
    for makefile in makefiles:        
        for k, v in makefile_targets(makefile).items():
            if k != 'exports' and isinstance(v, Target):
                if not v.name:
                    v.name = f'{makefile.name}.{k}'
                targets.add(v)                
    return {t.name: t for t in targets}


def include(name: str | Path, build_path: Path = None):
    global current_makefile, root_makefile
    if not root_makefile:
        assert type(name) == type(Path())
        module_path: Path = name / 'makefile.py'
        spec = importlib.util.spec_from_file_location(
            'root', module_path)
        name = 'root'
    else:
        module_path: Path = current_makefile.source_path / name / 'makefile.py'
        if not module_path.exists():
            module_path = current_makefile.source_path / f'{name}.py'
        spec = importlib.util.spec_from_file_location(
            f'{current_makefile.name}.{name}', module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name, build_path)
    spec.loader.exec_module(module)
    makefiles.append(current_makefile)
    exports = getattr(module, 'exports') if hasattr(
        module, 'exports') else None
    if current_makefile != root_makefile:
        current_makefile = current_makefile.parent
    return exports
