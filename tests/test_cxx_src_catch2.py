from tests import PyMakeBaseTest


class CXXCatch2Test(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/src/catch2', methodName)

    async def test_config(self):

        ########################################
        async with self.section("base build", clean=True) as make:
            config = make.root.requirements.find('catch2-config')
            await config.build()
            self.assertTrue(config.output.exists())
            modified_at = config.output.modification_time

            self.assertTrue(config.up_to_date)
            ########################################
            counter = config.options.get('counter')
            counter.value = not counter.value
            self.assertFalse(config.up_to_date)

        async with self.section("option modification => rebuild") as make:
            config = make.root.requirements.find('catch2-config')
            await config.build()
            self.assertTrue(config.output.younger_than(modified_at),
                            "an option change should trigger a re-build")
