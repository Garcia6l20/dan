import importlib
import logging
import shutil
import tempfile
import unittest
from build.lib.pymake.logging import Logging

from pymake.core import aiofiles
from pymake.core.include import MakeFile
from pymake.core.pathlib import Path
from pymake.core.cache import Cache
from pymake.core.target import Target
from pymake.cxx import get_default_toolchain
from pymake.cxx.toolchain import CompileCommands, Toolchain
from pymake.make import Make

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
        self.reset()
        # self._build_path.cleanup()
        # del self._build_path
        tracemalloc.stop()
        return super().tearDown()

    def reset(self):
        import gc

        Target.reset()
        Cache.reset()

        from pymake.core.include import _reset as context_reset
        context_reset()
        from pymake.cxx import _reset as cxx_reset
        cxx_reset()

        gc.collect()

        active_objects = list()
        for obj in gc.get_objects():
            if isinstance(obj, (Make, Target, MakeFile, Cache, CompileCommands, Toolchain)):                
                tb = tracemalloc.get_object_traceback(obj)
                self.warning(f'{obj} [{type(obj)}] still alive !\n{tb}')
                active_objects.append(obj)
        
        self.assertEqual(len(active_objects), 0)


    __section_separator = "==============================================================================="
    __section_center_width = len(__section_separator) - 4
    def section(self, desc):
        self.reset()
        print(f"\n{self.__section_separator}\n"
              f"= {desc: ^{self.__section_center_width}} ="
              f"\n{self.__section_separator}\n")

    async def clean(self):
        if self.build_path.exists():
            print(Path.cwd())
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
