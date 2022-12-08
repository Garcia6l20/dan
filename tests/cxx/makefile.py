#!/usr/bin/env python3

from pymake import cli, include
from pymake.cxx import target_toolchain

target_toolchain.cxx_flags.add('-std=c++17')

include('simple')
include('libraries')
include('qt')
# include('modules')
include('smc')

if __name__ == '__main__':
    cli()
