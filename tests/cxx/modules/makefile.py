#!/usr/bin/env python3
from pymake import cli
from pymake.cxx import Module, Executable

hello = Module(sources=['hello.cpp'])
use_hello = Executable(sources=['main.cpp'], dependencies=[hello])

if __name__ == '__main__':
    cli()
