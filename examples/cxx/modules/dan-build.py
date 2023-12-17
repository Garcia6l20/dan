from dan.cxx import Module, Executable, toolchain
from dan.logging import warning
    
if toolchain.has_cxx_compile_options('-std=c++20', '--modules-ts'):
    hello = Module('hello', sources=['hello.cpp'])
    Executable('use_hello', sources=['main.cpp'], dependencies=[hello])
else:
    warning('selected compiler does not support modules, skipped !')
