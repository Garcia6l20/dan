from dan import requires
from dan.cxx import Executable
from dan.testing import Test

fmt, = requires('fmt = 9')

class TestSpdlog(Test, Executable):
    name = 'test-spdlog'
    sources= 'test_spdlog.cpp',
    private_includes= '.',
    dependencies = 'spdlog >= 1.11',
