from pymake.cxx import Executable
from pymake.testing import Test

class Simple(Executable):
    name = 'simple'
    sources = 'test.cpp', 'main.cpp'
    private_includes = '.',
    options = {
        'greater': 'hello_pymake'
    }

    async def __initialize__(self):
        self.compile_definitions.add(f'SIMPLE_GREATER="{self.options["greater"]}"')
        await super().__initialize__()

class SimpleTest(Test):
    name = 'simple-test'
    executable = Simple
