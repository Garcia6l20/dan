#!/usr/bin/env python3

from pymake import cli
from pymake.cxx import Library, Executable
from copy import deepcopy

static = Library(sources=['lib.cpp'], public_includes=['.'])
statically_linked = Executable(sources=['main.cpp'], dependencies=static)
shared = Library(sources=['lib.cpp'], public_includes=['.'], static=False)
shared_linked = Executable(sources=['main.cpp'], dependencies=shared)

if __name__ == '__main__':
    cli()
