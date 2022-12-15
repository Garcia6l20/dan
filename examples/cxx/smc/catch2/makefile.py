from pymake import self, include
from pymake.cxx import Executable

catch2, = include('catch2')

Executable('test_catch2',
           sources=['test_catch2.cpp'],
           private_includes=['.'],
           dependencies=[catch2])
