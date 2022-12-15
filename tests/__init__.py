import logging
import unittest

from pymake.core import aiofiles
from pymake.core.pathlib import Path
from pymake.core.cache import Cache
from pymake.core.target import Target
from pymake.cxx import get_default_toolchain
from pymake.make import Make


class PyMakeBaseTest(unittest.IsolatedAsyncioTestCase):
    tests_path = Path(__file__).parent
    root_path = tests_path.parent
    source_path = root_path / 'examples'
    build_path = tests_path / 'build-unittest'

    def __init__(self, subproject: str = None, methodName: str = None) -> None:
        super().__init__(methodName)
        self.subproject = subproject
        if self.subproject:
            self.source_path = PyMakeBaseTest.source_path / self.subproject
            self.build_path = PyMakeBaseTest.build_path / self.subproject

    def setUp(self) -> None:
        self.reset()
        return super().setUp()

    def reset(self):
        Target.reset()
        Cache.reset()
        self.assertEqual(0, len(Target.all))

    __section_separator = "==============================================================================="
    __section_center_width = len(__section_separator) - 4
    def section(self, desc):
        self.reset()
        print(f"\n{self.__section_separator}\n"
              f"= {desc: ^{self.__section_center_width}} ="
              f"\n{self.__section_separator}\n")

    async def clean(self):
        if self.build_path.exists():
            await aiofiles.rmtree(self.build_path)

    async def configure(self,
                        toolchain=None,
                        build_type='release') -> Make:
        await self.clean()
        config = Cache(self.build_path / Make._config_name)
        config.source_path = str(self.source_path)
        config.build_path = str(self.build_path)
        config.toolchain = toolchain or get_default_toolchain()
        config.build_type = build_type
        await config.save()
        del config
