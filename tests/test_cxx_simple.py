from dan.core.pathlib import Path
from dan.core.settings import InstallMode
from tests import PyMakeBaseTest


class CXXSimpleTest(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/simple', methodName)

    async def test_build(self):

        ########################################
        async with self.section("base build", clean=True) as make:
            target = make.root.find('simple')
            await target.initialize()
            self.assertFalse(target.output.exists())
            await target.build()
            self.assertTrue(target.output.exists())
            modified_at = target.output.modification_time


        ########################################
        async with self.section("no-modification => no-rebuild") as make:
            target = make.root.find('simple')
            await target.build()
            self.assertTrue(target.output.exists())
            self.assertEqual(modified_at, target.output.modification_time,
                            "no modifications should NOT trigger a re-build")

            # update source
            src: Path = target.source_path / list(target.sources)[0]
            src.utime()

        ########################################
        async with self.section("source modification => rebuild") as make:
            target = make.root.find('simple')
            await target.build()
            self.assertTrue(target.output.younger_than(modified_at),
                            "a source modification should trigger a re-build")


    async def test_option_change(self):

        ########################################
        async with self.section("base build", clean=True) as make:
            target = make.root.find('simple')
            await target.initialize()
            self.assertFalse(target.output.exists())
            await target.build()
            self.assertTrue(target.output.exists())
            modified_at = target.output.modification_time
            sha1 = target.options.sha1
            
            # change option
            greater = target.options.get('greater')
            expected_output = '=== test ==='
            greater.value = expected_output
            self.assertNotEqual(sha1, target.options.sha1)

        ########################################
        async with self.section("option modification => rebuild") as make:
            target = make.root.find('simple')
            await target.build()
            self.assertTrue(target.output.younger_than(modified_at),
                            "an option change should trigger a re-build")
            modified_at = target.output.modification_time
            out, err, rc = await target.execute()
            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), f'{expected_output} !')

    async def test_install(self):

        ########################################
        async with self.section("install",
                                settings=[f"install.destination={self.build_path}/dist"]
                                ) as make:
            await make.initialize()
            await make.install(InstallMode.user)
            bins = list((self.build_path / 'dist/bin').glob('*'))
            self.assertEqual(len(bins), 1)
            self.assertEqual(bins[0].stem, 'simple')
