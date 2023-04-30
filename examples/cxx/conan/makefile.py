from pymake import self, requires
from pymake.cxx import Executable

zlib, boost = requires('zlib', 'boost')

class ZlibExample(Executable):
    name = 'zlib-example'
    sources= 'zlib-example.c',
    dependencies=zlib,
    test = True

class BoostExample(Executable):
    name = 'boost-example'
    sources= 'boost-example.cpp',
    dependencies= boost,
    test = {
        'args': [42, 12],
        'result': 6
    }
