from dan.core.pathlib import Path
from dan.core.settings import InstallMode
from tests import PyMakeBaseTest


class CXXSimpleTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/simple', methodName)

    async def test_build(self):

        ########################################
        async with self.section("base build", clean=True) as make:
            target, = make.get('dan-simple')
            await target.initialize()
            self.assertFalse(target.output.exists())
            await target.build()
            self.assertTrue(target.output.exists())
            self.modified_at = target.output.modification_time
            del make, target


        ########################################
        async with self.section("no-modification => no-rebuild") as make:
            target, = make.get('dan-simple')
            await target.build()
            self.assertTrue(target.output.exists())
            self.assertEqual(self.modified_at, target.output.modification_time,
                            "no modifications should NOT trigger a re-build")

            # update source
            src: Path = target.source_path / list(target.sources)[0]
            src.utime()
            del make, target

        ########################################
        async with self.section("source modification => rebuild") as make:
            target, = make.get('dan-simple')
            await target.build()
            self.assertTrue(target.output.younger_than(self.modified_at),
                            "a source modification should trigger a re-build")
            self.modified_at = target.output.modification_time

            # change option
            greater = target.options.get('greater')
            expected_output = '=== test ==='
            greater.value = expected_output
            await target.makefile.cache.save()
            del make, target, greater

        ########################################
        async with self.section("option modification => rebuild") as make:
            target, = make.get('dan-simple')
            await target.build()
            self.assertTrue(target.output.younger_than(self.modified_at),
                            "an option change should trigger a re-build")
            self.modified_at = target.output.modification_time
            out, err, rc = await target.execute()
            self.assertEqual(rc, 0)
            self.assertEqual(out, f'{expected_output} !\n')

            del make, target


    async def test_install(self):

        ########################################
        async with self.section("install") as make:
            make.apply_settings(f"install.destination={self.build_path}/dist")
            await make.initialize()
            await make.install(InstallMode.user)
            self.assertTrue((self.build_path / 'dist/bin/dan-simple').exists())

            del make
