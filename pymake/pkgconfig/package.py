from pathlib import Path
import pkgconfig

class MissingPackage(RuntimeError):
    def __init__(self, name) -> None:
        super().__init__(f'package {name} not found')

class Package:
    def __init__(self, name, minimum_version = None, pc_file : Path = None) -> None:
        self.name = name
        # if pc_file:
        #     pkgconfig.
        # else:
        if not pkgconfig.exists(self.name):
            raise MissingPackage(self.name)
