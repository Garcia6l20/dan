from pymake import self
from pymake.cxx.support.qt import QtExecutable

exe = QtExecutable('pymake-qt-example',
                   qt_modules=['Widgets'],
                   sources=['main.cpp', 'mainwindow.cpp'],
                   private_includes=['.'])
self.install(exe)
