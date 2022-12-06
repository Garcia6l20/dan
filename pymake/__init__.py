# patch root makefile
root_makefile = None
if not root_makefile:
    import sys
    import inspect
    from pathlib import Path
    root_makefile = sys.modules['__main__']
    setattr(root_makefile, 'source_path', Path(root_makefile.__file__).parent)

from .core.target import target
from .cli import cli
