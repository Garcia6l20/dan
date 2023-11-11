from dan.cxx import Executable

class InvalidSyntax(Executable):
    sources = ['invalid-syntax.cpp']

class NoMain(Executable):
    sources = ['no-main.cpp']

class UndefinedReference(Executable):
    sources = ['undefined-reference.cpp']

class IncludeChain(Executable):
    private_includes = ['.']
    sources = ['include-chain.cpp']

class TemplateError(Executable):
    private_includes = ['.']
    sources = ['template-error.cpp']
