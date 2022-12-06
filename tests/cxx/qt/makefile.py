#!/usr/bin/env python3

from pymake import cli
from pymake.cxx import Library, Executable
from pymake.pkgconfig import Package

qt_widgets = Package('Qt5Widgets')
qt_example = Executable(sources=['main.cpp'],
                      dependencies=[qt_widgets],
                      private_compile_options=['-fPIC'])

if __name__ == '__main__':
    cli()
