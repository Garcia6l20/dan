from pymake import self, requires
from pymake.cxx import Executable

requires('fmt', 'spdlog')

class TestSpdlog(Executable):
    name = 'test-spdlog'
    sources= 'test_spdlog.cpp',
    private_includes= '.',
    dependencies = 'spdlog',
    is_test = True
