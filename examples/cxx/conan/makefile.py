from pymake import requires
from pymake.cxx import Executable
from pymake.testing import Test

zlib, boost = requires('zlib', 'boost')

class ZlibExample(Test, Executable):
    name = 'zlib-example'
    sources= 'zlib-example.c',
    dependencies=zlib,


class BoostExample(Test, Executable):
    name = 'boost-example'
    sources= 'boost-example.cpp',
    dependencies= boost,    
    cases = [
        ((42, 12), 6),
        ((44, 8), 4),
        ((142, 42), 2),
    ]
