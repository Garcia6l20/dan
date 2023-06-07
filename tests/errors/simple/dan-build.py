from dan.cxx import Executable

class InvalidSyntax(Executable):
    sources = ['invalid-syntax.cpp']

class NoMain(Executable):
    sources = ['no-main.cpp']

class UndefinedReference(Executable):
    sources = ['undefined-reference.cpp']
