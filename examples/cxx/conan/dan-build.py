from dan import requires
from dan.cxx import Executable
from dan.testing import Test, Case

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
        Case('42-12', 42, 12, expected_result=6),
        Case('44-8', 44, 8, expected_result=4),
        Case('142-42', 142, 42, expected_result=2),
    ]
