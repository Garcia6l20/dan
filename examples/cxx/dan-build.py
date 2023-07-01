from dan import self, include
from dan.cxx import target_toolchain

target_toolchain.cpp_std = 17

include('simple')
include('libraries')
include('qt')
# include('modules')
with_src = self.options.add('with_src', False, help='Enable src examples')
if with_src.value:
    include('src')

with_conan = self.options.add('with_conan', False, help='Enable conan examples')
if with_conan.value:
    include('conan')

include('dan.io')
# include('webview')
