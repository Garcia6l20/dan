from pymake import self
from pymake.cxx.support.qt import QtExecutable
from pymake.pkgconfig import has_package

if has_package('Qt5Core'):
    exe = QtExecutable('pymake-qt-example',
                    qt_modules=['Widgets'],
                    sources=['main.cpp', 'mainwindow.cpp'],
                    private_includes=['.'])
    self.install(exe)
