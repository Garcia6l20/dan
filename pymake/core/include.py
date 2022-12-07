import importlib.util
from pathlib import Path

from pymake.core.logging import setup_logger, logging

# patch root makefile
root_makefile = None
current_makefile = None
makefiles = list()


def _init_makefile(module, name: str = 'root'):
    global current_makefile
    source_path = Path(module.__file__).parent
    if module != root_makefile:
        build_path = current_makefile.build_path / name
        name = f'{current_makefile.name}.{name}'
    else:
        build_path = source_path / 'build'

    setattr(module, 'source_path', source_path)
    setattr(module, 'build_path', build_path)
    setattr(module, 'parent_makefile', current_makefile)
    setattr(module, 'name', name)
    logger = logging.getLogger(name)
    setup_logger(logger)
    setattr(module, '_logger', logger)
    setattr(module, 'debug', logger.debug)
    setattr(module, 'info', logger.info)
    setattr(module, 'warning', logger.warning)
    setattr(module, 'error', logger.error)
    setattr(module, 'critical', logger.critical)
    current_makefile = module


if not root_makefile:
    import sys
    from pathlib import Path
    root_makefile = sys.modules['__main__']
    _init_makefile(root_makefile)
    current_makefile = root_makefile
    makefiles.append(current_makefile)


def targets():
    from pymake.core.target import Target
    targets: dict[str, Target] = dict()
    for makefile in makefiles:
        for k, v in makefile.__dict__.items():
            if isinstance(v, Target):
                targets[f'{makefile.name}.{k}'] = v
    return targets


def include(name: str):
    global current_makefile
    module_path = current_makefile.source_path / name / 'makefile.py'
    spec = importlib.util.spec_from_file_location(
        f'{current_makefile.name}.{name}', module_path)
    module = importlib.util.module_from_spec(spec)
    _init_makefile(module, name)
    spec.loader.exec_module(module)
    makefiles.append(current_makefile)
    current_makefile = current_makefile.parent_makefile
