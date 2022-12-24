from pymake import self, requires
from pymake.cxx import Executable

example = Executable('pymake-test-catch2',
                     sources=['test_catch2.cpp'],
                     private_includes=['.'],
                     dependencies=requires('catch2'))
self.add_test(example)
self.install(example)
