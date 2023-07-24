from dan.cxx import Executable
from dan.cxx.support import qt
from dan.pkgconfig import has_package

if has_package('Qt6Core'):
    @qt.moc(modules = ['Widgets'])
    class QtExample(Executable):
        name = 'dan-qt-example'
        sources = 'main.cpp', 'mainwindow.cpp'
        private_includes = ['.']
