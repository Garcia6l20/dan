import unittest
from dan.logging import Logging

from dan.core import aiofiles
from dan.core.pathlib import Path
from dan.core.cache import Cache
from dan.cxx import get_default_toolchain
from dan.make import Make

import tracemalloc


class PyMakeBaseTest(unittest.IsolatedAsyncioTestCase, Logging):
    tests_path = Path(__file__).parent
    root_path = tests_path.parent
    source_path = root_path / 'examples'
    build_path = tests_path / 'build-unittest'

    def __init__(self, subproject: str = None, methodName: str = None) -> None:
        Logging.__init__(self, self.__class__.__name__)
        unittest.IsolatedAsyncioTestCase.__init__(self, methodName)
        PyMakeBaseTest.build_path.mkdir(exist_ok=True, parents=False)
        self.subproject = subproject
        if self.subproject:
            self.source_path = PyMakeBaseTest.source_path / self.subproject
            self.build_path = PyMakeBaseTest.build_path / self.subproject

    def setUp(self) -> None:
        return super().setUp()

    def tearDown(self) -> None:
        return super().tearDown()

    class __MakeSection:
        __section_separator = "==============================================================================="
        __section_center_width = len(__section_separator) - 4

        def __init__(self,
                     test: 'PyMakeBaseTest',
                     desc: str,
                     options: list[str],
                     settings: list[str],
                     clean: bool,
                     init: bool) -> None:
            self.test = test
            self.desc = desc
            self.clean = clean
            self.options = options
            self.settings = settings
            self.init = init

        async def __aenter__(self):
            print(f"\n{self.__section_separator}\n"
                  f"= {self.desc: ^{self.__section_center_width}} ="
                  f"\n{self.__section_separator}\n")
            if self.clean:
                await self.test.clean()
                make = Make(self.test.build_path, verbose=True)
                await make.configure(self.test.source_path, get_default_toolchain())
            else:
                make = Make(self.test.build_path, verbose=True)
            if len(self.options) or len(self.settings):
                await make.initialize()
                if len(self.options):
                    await make.apply_options(*self.options)
                if len(self.settings):
                    await make.apply_settings(*self.settings)
                await Cache.save_all()
                del make
                self.test.reset()
                make = Make(self.test.build_path, verbose=True)
            
            if self.init:
                await make.initialize()

            return make

        async def __aexit__(self, exc_type, exc, tb):
            await Cache.save_all()
            Cache.clear_all()

    def section(self, desc: str, options=list(), settings=list(), clean=False, init=True):
        return self.__MakeSection(self, desc, options, settings, clean, init)

    async def clean(self):
        if self.build_path.exists():
            print(f'cleaning: {self.build_path}')
            await aiofiles.rmtree(self.build_path, force=True)
