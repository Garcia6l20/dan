from pymake.core.pathlib import Path
from tests import PyMakeBaseTest


class CXXSimpleLibTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/libraries', methodName)

    async def test_build(self):
        target_name = 'pymake-simple-lib'

        ########################################
        async with self.section("base build", clean=True) as make:
            target, = make.get(target_name)
            await target.initialize()
            self.assertFalse(target.output.exists())
            await target.build()
            self.assertTrue(target.output.exists())
            self.modified_at = target.output.modification_time

            del make, target

        ########################################
        async with self.section("no-modification => no-rebuild") as make:
            target, = make.get(target_name)
            await target.build()
            self.assertTrue(target.output.exists())
            self.assertEqual(self.modified_at, target.output.modification_time,
                            "no modifications should NOT trigger a re-build")

            # update source
            src: Path = target.source_path / list(target.sources)[0]
            src.utime()

            del make, target

        async with self.section("source modification => rebuild") as make:
            target, = make.get(target_name)
            await target.build()
            self.assertTrue(target.output.younger_than(self.modified_at),
                            "a source modification should trigger a re-build")
            self.modified_at = target.output.modification_time

            del make, target
