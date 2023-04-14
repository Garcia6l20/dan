from tests import PyMakeBaseTest


class CXXCatch2Test(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__('cxx/smc/catch2', methodName)

    async def test_config(self):
        target_name = 'root.catch2.catch2.config'

        ########################################
        async with self.section("base build", clean=True) as make:
            target, = make.get(target_name)
            await target.initialize()
            await target.build()
            self.assertTrue(target.output.exists())
            self.modified_at = target.output.modification_time

            ########################################
            counter = target.options.get('counter')
            counter.value = not counter.value
            
            del make, target, counter

        async with self.section("option modification => rebuild") as make:
            target, = make.get(target_name)
            await target.initialize()
            await target.build()
            self.assertTrue(target.output.younger_than(self.modified_at),
                            "an option change should trigger a re-build")
            self.modified_at = target.output.modification_time

            del make, target

    async def test_build(self):

        ########################################
        async with self.section("base build", clean=True) as make:
            target, = make.get('catch2')
            await target.initialize()
            self.assertFalse(target.output.exists())
            await target.build()
            self.assertTrue(target.output.exists())
            self.modified_at = target.output.modification_time

            ########################################
            counter = target.options.get('console_width')
            counter.value = counter.value + 20

            del make, target, counter

        async with self.section("option modification => rebuild") as make:
            target, = make.get('catch2')
            await target.build()
            self.assertTrue(target.output.younger_than(self.modified_at),
                            "an option change should trigger a re-build")
            self.modified_at = target.output.modification_time

            del make, target
