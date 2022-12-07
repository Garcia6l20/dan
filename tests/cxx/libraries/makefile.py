#!/usr/bin/env python3

from pymake import cli
from pymake.cxx import Library, Executable, Objects
from copy import deepcopy

compile_options = {'-std=c++17'}

objects = Objects(sources=['static.cpp'], public_includes=[
                  '.'], public_compile_options=compile_options)

static = Library(sources=[],
                 public_includes=['.'],
                 public_compile_options=compile_options,
                 dependencies=[objects])

statically_linked = Executable(sources=['main.cpp'], dependencies=[static])

shared = Library(sources=[],
                 public_includes=['.'],
                 static=False,
                 public_compile_options=compile_options,
                 dependencies=[objects])

shared_linked = Executable(sources=['main.cpp'], dependencies=[shared])

if __name__ == '__main__':
    cli()
