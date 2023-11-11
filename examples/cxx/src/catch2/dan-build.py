from dan import requires
from dan.cxx import Executable

catch2, = requires('catch2 = 3')


@catch2.discover_tests
class UseCatch2(Executable):
    sources = 'test_catch2.cpp',
    dependencies = ['catch2-with-main']
