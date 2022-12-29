from pymake import self, requires, load
from pymake.cxx import Executable

load('spdlog')

exe = Executable('test_spdlog',
                 sources=['test_spdlog.cpp'],
                 private_includes=['.'],
                 dependencies=requires('spdlog')
                 )
self.add_test(exe)
