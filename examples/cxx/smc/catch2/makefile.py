from pymake import self, requires
from pymake.cxx import Executable
import platform

catch2, = requires('catch2')

example = Executable('pymake-test-catch2',
                     sources=['test_catch2.cpp'],
                     private_includes=['.'],
                     dependencies=[catch2])

catch2.discover_tests(example)

if platform.system() == 'Windows':
    example.link_options.add('/SUBSYSTEM:CONSOLE')

self.install(example)
