from pymake import self, requires
from pymake.cxx import Executable

exe = Executable('test_spdlog',
                 sources=['test_spdlog.cpp'],
                 private_includes=['.'],
                 dependencies=requires('spdlog')
                 )
self.add_test(exe)
