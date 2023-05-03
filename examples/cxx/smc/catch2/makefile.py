from pymake import requires
from pymake.cxx import Executable

catch2, = requires('catch2')


class UseCatch2(Executable):
    sources = 'test_catch2.cpp',
    dependencies = [catch2]

catch2.discover_tests(UseCatch2)
