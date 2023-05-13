from pymake import self
from pymake.cxx import Executable
from pymake.testing import Test, Case
import re

class Simple(Executable):
    name = 'simple'
    sources = 'test.cpp', 'main.cpp'
    private_includes = '.',
    options = {
        'greater': ('hello_pymake', 'The name to be greated.')
    }

    async def __initialize__(self):
        self.compile_definitions.add(f'SIMPLE_GREATER="{self.options["greater"]}"')
        await super().__initialize__()

class SimpleTest(Test):
    name = 'simple-test'
    executable = Simple
    cases = [
        Case('default', expected_output=re.compile(fr'^{self[Simple].options["greater"]} !\s'), strip_output=False)
    ]
