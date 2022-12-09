#!/usr/bin/env python3

from pymake import cli
from pymake.logging import warning
from pymake.cxx import Executable
from pymake.pkgconfig import Package, MissingPackage

try:
    qt_widgets = Package('Qt5Widgets')
    qt_example = Executable(sources=['main.cpp'],
                        dependencies=[qt_widgets],
                        private_compile_options=['-fPIC'])
except MissingPackage:
    warning('cannot find Qt5Widgets package, sipping !')

if __name__ == '__main__':
    cli()
