from pymake.core.pathlib import Path
from pymake.core.target import Target
from pymake.make import Make
from tests import PyMakeBaseTest


class CXXSimpleTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/simple', methodName)

    async def test_build(self):

        ########################################
        self.section("base build")
        await self.configure()
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get('pymake-simple')
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
        target, = Target.get('pymake-simple')
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
        target, = Target.get('pymake-simple')
        await target.build()
        self.assertTrue(target.output.younger_than(self.modified_at),
                        "a source modification should trigger a re-build")
        self.modified_at = target.output.modification_time

        ########################################
        greater = target.options.get('greater')
        expected_output = '=== test ==='
        greater.value = expected_output
        await target.makefile.cache.save()

        del make, target, greater
        self.section("option modification => rebuild")
        make = Make(self.build_path, verbose=True)
        await make.initialize()
        target, = Target.get('pymake-simple')
        await target.build()
        self.assertTrue(target.output.younger_than(self.modified_at),
                        "an option change should trigger a re-build")
        self.modified_at = target.output.modification_time
        out, err, rc = await target.execute(pipe=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, f'{expected_output} !\n')

        del make, target

    # async def test_install(self):

    #     ########################################
    #     self.section("install")
    #     await self.configure()
    #     make = Make(self.build_path, verbose=True)
    #     await make.initialize()
    #     await make.install(self.build_path / 'dist')
    #     self.assertTrue((self.build_path / 'dist/bin/pymake-simple').exists())

    #     del make, target
