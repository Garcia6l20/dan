#!/usr/bin/env python3
from pymake import cli
from pymake.cxx import Module, Executable, target_toolchain
from pymake.cxx.targets import CXXObjectsTarget
    
if target_toolchain.has_cxx_compile_options('-std=c++20', '--modules-ts'):
    hello = Module(sources=['hello.cpp'])
    use_hello = Executable(sources=['main.cpp'], dependencies=[hello])
else:
    warning('selected compiler does not support modules, skipped !')

if __name__ == '__main__':
    cli()
