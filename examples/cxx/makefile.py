from pymake import include
from pymake.cxx import target_toolchain

target_toolchain.cpp_std = 17

include('simple')
include('libraries')
include('qt')
# include('modules')
include('smc')
include('conan')
include('pymake.io')
