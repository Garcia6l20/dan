from pymake import self, requires
from pymake.cxx import Executable

zlib, = requires('zlib')

example = Executable('zlib-example',
                     sources=[
                         'zlib-example.c',
                     ],
                     dependencies=[zlib])
self.add_test(example)
