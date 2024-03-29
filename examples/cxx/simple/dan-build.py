from dan.cxx import Executable
from dan.testing import Test, Case
import re

class Simple(Executable):
    name = 'simple'
    sources = 'test.cpp', 'main.cpp'
    private_includes = '.',
    options = {
        'greater': ('hello_dan', 'The name to be greated.')
    }
    installed = True

    async def __initialize__(self):
        self.compile_definitions.add(f'SIMPLE_GREATER="{self.options["greater"]}"')
        await super().__initialize__()

class SimpleTest(Test):
    name = 'simple-test'
    executable = Simple
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = [
            Case('default', expected_output=re.compile(fr'^{self.executable.options["greater"]} !\s'), strip_output=False)
        ]
