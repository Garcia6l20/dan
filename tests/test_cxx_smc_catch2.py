import os
from pymake.core import asyncio
from pymake.core.cache import Cache
from pymake.core.pathlib import Path
from pymake.core.target import Target
from pymake.cxx.targets import Executable
from pymake.make import Make
from tests import PyMakeBaseTest


class CXXCatch2Test(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/smc/catch2', methodName)

    async def test_config(self):
        target_name = 'root.catch2.catch2.config'

        ########################################
        self.section("base build")
        await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        
        target, = Target.get(target_name)
        await target.initialize()
        await target.build()
        self.assertTrue(target.output.exists())
        self.modified_at = target.output.modification_time

        ########################################
        counter = target.options.get('counter')
        counter.value = not counter.value
        await Cache.save_all()

        del make, target, counter

        self.section("option modification => rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get(target_name)
        await target.initialize()
        await target.build()
        self.assertTrue(target.output.younger_than(self.modified_at),
                        "an option change should trigger a re-build")
        self.modified_at = target.output.modification_time

        del make, target

    async def test_build(self):

        ########################################
        self.section("base build")
        make = await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get('catch2')
        await target.initialize()
        self.assertFalse(target.output.exists())
        await target.build()
        self.assertTrue(target.output.exists())
        self.modified_at = target.output.modification_time

        ########################################
        counter = target.options.get('console_width')
        counter.value = counter.value + 20
        await Cache.save_all()

        del make, target, counter

        self.section("option modification => rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get('catch2')
        await target.build()
        self.assertTrue(target.output.younger_than(self.modified_at),
                        "an option change should trigger a re-build")
        self.modified_at = target.output.modification_time

        del make, target