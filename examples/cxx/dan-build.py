from dan import include
from dan.cxx import target_toolchain

target_toolchain.cpp_std = 17

include('simple')
include('libraries')
include('qt')
# include('modules')
include('src')
include('conan')
include('dan.io')
