from pymake import requires
from pymake.cxx import Executable

catch2, = requires('catch2 = 3')

@catch2.discover_tests
class UseCatch2(Executable):
    sources = 'test_catch2.cpp',
    dependencies = [
        catch2,
        'spdlog >= 1.11',
    ]
