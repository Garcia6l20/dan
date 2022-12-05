from .core.target import target

# patch root makefile
source_root = None
root_module = None
if not root_module:
    import sys
    import inspect
    from pathlib import Path
    root_module = sys.modules['__main__']
    source_root = Path(root_module.__file__).parent
    from .cli import cli
    setattr(root_module, '__main__', cli)
