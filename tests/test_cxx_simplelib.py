from pymake.core.pathlib import Path
from pymake.core.target import Target
from pymake.make import Make
from tests import PyMakeBaseTest


class CXXSimpleLibTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/libraries', methodName)

    async def test_build(self):
        target_name = 'pymake-simple-lib'

        ########################################
        self.section("base build")
        await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get(target_name)
        await target.initialize()
        self.assertFalse(target.output.exists())
        await target.build()
        self.assertTrue(target.output.exists())
        self.modified_at = target.output.modification_time

        del make, target

        ########################################
        self.section("no-modification => no-rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get(target_name)
        await target.build()
        self.assertTrue(target.output.exists())
        self.assertEqual(self.modified_at, target.output.modification_time,
                        "no modifications should NOT trigger a re-build")

        ########################################
        src: Path = target.source_path / list(target.sources)[0]
        src.utime()

        del make, target

        self.section("source modification => rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get(target_name)
        await target.build()
        self.assertTrue(target.output.younger_than(self.modified_at),
                        "a source modification should trigger a re-build")
        self.modified_at = target.output.modification_time
