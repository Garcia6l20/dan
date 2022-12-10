import importlib.util
from pathlib import Path

# patch root makefile
root_makefile = None
current_makefile = None
makefiles = list()


def _init_makefile(module, name: str = 'root', build_path: Path = None):
    global current_makefile
    source_path = Path(module.__file__).parent
    if module != root_makefile:
        build_path = build_path or current_makefile.build_path / name
        name = f'{current_makefile.name}.{name}'
    else:
        assert build_path
    build_path.mkdir(parents=True, exist_ok=True)

    setattr(module, 'source_path', source_path)
    setattr(module, 'build_path', build_path)
    setattr(module, 'parent_makefile', current_makefile)
    setattr(module, 'name', name)
    current_makefile = module


def targets():
    from pymake.core.target import Target
    targets: dict[str, Target] = dict()
    for makefile in makefiles:
        for k, v in makefile.__dict__.items():
            if isinstance(v, Target):
                targets[f'{makefile.name}.{k}'] = v
    return targets


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
    if not root_makefile:
        current_makefile = root_makefile = module
    _init_makefile(module, name, build_path)
    spec.loader.exec_module(module)
    makefiles.append(current_makefile)
    exports = getattr(module, 'exports') if hasattr(
        module, 'exports') else None
    if current_makefile != root_makefile:
        current_makefile = current_makefile.parent_makefile
    return exports
