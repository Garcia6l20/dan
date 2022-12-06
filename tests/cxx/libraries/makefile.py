#!/usr/bin/env python3

from pymake import cli
from pymake.cxx import Library, Executable
from copy import deepcopy

compile_options = {'-std=c++17'}

static = Library(sources=['static.cpp'], public_includes=['.'], public_compile_options=compile_options)
statically_linked = Executable(sources=['main.cpp'], dependencies=[static])
shared = Library(sources=['shared.cpp'], public_includes=['.'], static=False, public_compile_options=compile_options)
shared_linked = Executable(sources=['main.cpp'], dependencies=[shared])

if __name__ == '__main__':
    cli()
