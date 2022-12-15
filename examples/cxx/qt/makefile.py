from pymake import self
from pymake.logging import warning
from pymake.cxx import Executable
from pymake.pkgconfig import Package, MissingPackage

try:
    qt_widgets = Package('Qt5Widgets')
    exe = Executable('pymake-qt-example',
                     sources=['main.cpp'],
                     dependencies=[qt_widgets],
                     private_compile_options=['-fPIC'])
    self.install(exe)
except MissingPackage:
    warning('cannot find Qt5Widgets package, skipping !')
