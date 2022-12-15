import os
import shutil
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

    def tearDown(self) -> None:
        if (self.build_path / 'dist').exists():
            shutil.rmtree(self.build_path / 'dist')
        return super().tearDown()

    async def test_build(self):

        ########################################
        self.section("base build")
        make = await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        simple, = Target.get('pymake-simple')
        await simple.initialize()
        self.assertFalse(simple.output.exists())
        await simple.build()
        self.assertTrue(simple.output.exists())
        self.modified_at = simple.output.modification_time

        ########################################
        self.section("no-modification => no-rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        simple, = Target.get('pymake-simple')
        await simple.build()
        self.assertTrue(simple.output.exists())
        self.assertEqual(self.modified_at, simple.output.modification_time,
                        "no modifications should NOT trigger a re-build")

        ########################################
        self.section("source modification => rebuild")
        src: Path = simple.source_path / list(simple.sources)[0]
        src.utime()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        simple, = Target.get('pymake-simple')
        await simple.build()
        self.assertTrue(simple.output.younger_than(self.modified_at),
                        "a source modification should trigger a re-build")
        self.modified_at = simple.output.modification_time

        ########################################
        greater = simple.options.get('greater')
        expected_output = '=== test ==='
        greater.value = expected_output
        await simple.makefile.cache.save()

        self.section("option modification => rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        simple, = Target.get('pymake-simple')
        await simple.build()
        self.assertTrue(simple.output.younger_than(self.modified_at),
                        "an option change should trigger a re-build")
        self.modified_at = simple.output.modification_time
        out, err, rc = await simple.execute(pipe=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, f'{expected_output} !\n')


    async def test_install(self):

        ########################################
        self.section("install")
        make = await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        await make.install(self.build_path / 'dist')
        self.assertTrue((self.build_path / 'dist/bin/pymake-simple').exists())
