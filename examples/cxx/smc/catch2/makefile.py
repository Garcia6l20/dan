from pymake import self, requires, load
from pymake.cxx import Executable

load('catch2')

catch2 = requires('catch2')[0]

example = Executable('pymake-test-catch2',
                     sources=['test_catch2.cpp'],
                     private_includes=['.'],
                     dependencies=[catch2])

catch2.discover_tests(example)

self.install(example)
