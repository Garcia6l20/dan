from pymake import self, requires
from pymake.cxx import Executable

zlib, boost = requires('zlib', 'boost')

example = Executable('zlib-example',
                     sources=[
                         'zlib-example.c',
                     ],
                     dependencies=[zlib])
self.add_test(example)

example = Executable('boost-example',
                     sources=['boost-example.cpp'],
                     dependencies=[boost])
self.add_test(example, args=['42', '12'], expected_result=6)
