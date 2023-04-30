from pymake.cxx import Executable

class Simple(Executable):
    name = 'simple'
    sources = 'test.cpp', 'main.cpp'
    private_includes = '.',
    options = {
        'greater': 'hello_pymake'
    }
    is_test = True
    install = True

    async def __initialize__(self):
        self.compile_definitions.add(f'SIMPLE_GREATER="{self.options["greater"]}"')
        await super().__initialize__()
