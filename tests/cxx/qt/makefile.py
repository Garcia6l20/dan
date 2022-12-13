from pymake.logging import warning
from pymake.cxx import Executable
from pymake.pkgconfig import Package, MissingPackage

try:
    qt_widgets = Package('Qt5Widgets')
    Executable('qt_example',
               sources=['main.cpp'],
               dependencies=[qt_widgets],
               private_compile_options=['-fPIC'])
except MissingPackage:
    warning('cannot find Qt5Widgets package, skipping !')
