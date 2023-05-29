import sys
import unittest
from dan.core.test import Test
from dan.logging import Logging

from dan.core import aiofiles
from dan.core.include import MakeFile
from dan.core.pathlib import Path
from dan.core.cache import Cache
from dan.core.target import Target
from dan.cxx import get_default_toolchain
from dan.cxx.toolchain import CompileCommands, Toolchain
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
        tracemalloc.start()
        # self._build_path = tempfile.TemporaryDirectory(prefix=self.subproject.replace('/', '.') + '-', dir=PyMakeBaseTest.build_path)
        # self.build_path = Path(self._build_path.name)
        self.reset()
        return super().setUp()

    def tearDown(self) -> None:
        self.reset(False)
        # self._build_path.cleanup()
        # del self._build_path
        tracemalloc.stop()
        return super().tearDown()

    def reset(self, check_still_alive=True, autodelete=True):
        import gc

        from dan.core.include import context_reset
        context_reset()
        Cache.clear_all()

        gc.collect()
        
        auto_delete_classes = (Make, Target, Test, MakeFile, Cache, CompileCommands, Toolchain)
        if autodelete:
            for obj in gc.get_objects():
                if isinstance(obj, auto_delete_classes):
                    del obj

            gc.collect()

        if check_still_alive:
            active_objects = list()
            for obj in gc.get_objects():
                if isinstance(obj, auto_delete_classes):
                    tb = tracemalloc.get_object_traceback(obj)
                    if tb is not None:
                        tb = f'\nobject traceback: {tb}'
                    else:
                        tb = ''
                    self.warning(
                        f'{obj} [{type(obj)}] still alive ({sys.getrefcount(obj) - 1} references) !{tb}')
                    active_objects.append(obj)

            self.assertEqual(len(active_objects), 0)

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
                await self.test.configure()
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
            # self.test.reset(check_still_alive=exc_type is None)

    def section(self, desc: str, options=list(), settings=list(), clean=False, init=True):
        return self.__MakeSection(self, desc, options, settings, clean, init)

    async def clean(self):
        if self.build_path.exists():
            print(f'cleaning: {self.build_path}')
            await aiofiles.rmtree(self.build_path, force=True)

    async def configure(self,
                        toolchain=None) -> Make:
        await self.clean()
        from dan.make import ConfigCache
        config = ConfigCache(self.build_path / Make._config_name)
        config.data.source_path = str(self.source_path)
        config.data.build_path = str(self.build_path)
        config.data.toolchain = toolchain or get_default_toolchain()
        await config.save()
        config.ignore()
        del config
