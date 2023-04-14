from pymake import self, requires
from pymake.cxx import Executable

requires('fmt', 'spdlog')

exe = Executable('test_spdlog',
                 sources=['test_spdlog.cpp'],
                 private_includes=['.'],
                 dependencies=['spdlog']
                 )
self.add_test(exe)
