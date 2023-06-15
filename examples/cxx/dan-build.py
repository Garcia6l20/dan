from dan import self, include
from dan.cxx import target_toolchain

target_toolchain.cpp_std = 17

include('simple')
include('libraries')
include('qt')
# include('modules')
include('src')
with_conan = self.options.add('with_conan', False, help='Enable conan examples')
if with_conan.value:
    include('conan')

include('dan.io')
