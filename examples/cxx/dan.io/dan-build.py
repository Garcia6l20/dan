from dan import requires
from dan.cxx import Executable
from dan.testing import Test

catch2, = requires('catch2 = 3')

@catch2.discover_tests
class UseCatch2(Executable):
    sources = 'test_catch2.cpp',
    dependencies = [
        catch2,
        'spdlog >= 1.11',
    ]


class TestSpdlog(Test, Executable):
    name = 'test-spdlog'
    sources= 'test_spdlog.cpp',
    private_includes= '.',
    dependencies = 'spdlog >= 1.11',
