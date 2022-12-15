import os
from pymake.core import asyncio
from pymake.core.cache import Cache
from pymake.core.pathlib import Path
from pymake.core.target import Target
from pymake.cxx.targets import Executable
from pymake.make import Make
from tests import PyMakeBaseTest


class CXXSimpleTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/simple', methodName)

    def section(self, desc):
        self.reset()
        separator = "=================================================="
        center_width = len(separator) - 4
        print(f"\n{separator}\n"
              f"= {desc: ^{center_width}} ="
              f"\n{separator}\n")

    async def test_build(self):

        ########################################
        self.section("base build")
        make = await self.configure()
        make = Make(self.build_path)
        await make.initialize()
        simple, = Target.get('simple')
        await simple.initialize()

        self.assertFalse(simple.output.exists())
        await simple.build()
        self.assertTrue(simple.output.exists())
        self.modified_at = simple.output.modification_time

        ########################################
        self.section("no-modification => no-rebuild")
        make = Make(self.build_path)
        await make.initialize()
        simple, = Target.get('simple')
        await simple.initialize()
        self.assertTrue(simple.output.exists())
        self.assertEqual(self.modified_at, simple.output.modification_time)

        ########################################
        self.section("source modification => rebuild")
        src: Path = simple.source_path / list(simple.sources)[0]
        src.utime()
        await simple.build()
        self.assertLess(self.modified_at, simple.output.modification_time)

        ########################################
        self.section("option modification => rebuild")
        src: Path = simple.source_path / list(simple.sources)[0]
        src.utime()
        await simple.build()
        self.assertLess(self.modified_at, simple.output.modification_time)
