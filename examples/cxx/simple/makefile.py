from pymake.cxx import Executable

Executable('simple', sources=['test.cpp', 'main.cpp'], private_includes=['.'])
