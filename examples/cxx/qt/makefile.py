from pymake import self
from pymake.cxx import Executable
from pymake.cxx.support import qt
from pymake.pkgconfig import has_package

if has_package('Qt5Core'):
    @qt.moc(modules = ['Widgets'])
    class QtExample(Executable):
        name = 'pymake-qt-example'
        sources = 'main.cpp', 'mainwindow.cpp'
        private_includes = ['.']
