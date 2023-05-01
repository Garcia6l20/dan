from pymake import requires
from pymake.cxx import Executable
from pymake.testing import Test

catch2, = requires('catch2')


class UseCatch2(Test, Executable):
    sources = 'test_catch2.cpp',
    dependencies = [catch2]
