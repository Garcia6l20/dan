from pymake import requires
from pymake.cxx import Executable
from pymake.testing import Test

requires('fmt', 'spdlog')

class TestSpdlog(Test, Executable):
    name = 'test-spdlog'
    sources= 'test_spdlog.cpp',
    private_includes= '.',
    dependencies = 'spdlog',
