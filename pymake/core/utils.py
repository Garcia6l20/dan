from pathlib import Path
import os

class chdir:
    def __init__(self, path: Path, create = True):
        self.path = path
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        self.prev = None

    def __enter__(self):
        self.prev = Path.cwd()
        os.chdir(self.path)
        return None
    
    def __exit__(self, *args):
        os.chdir(self.prev)
