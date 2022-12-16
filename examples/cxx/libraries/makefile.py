from pymake import self
from pymake.cxx import Library, Executable, LibraryType, target_toolchain

target_toolchain.cpp_std = 17

sources = ['lib.cpp']
includes=['.']

# makefile-scope option
self.options.add('library_type', LibraryType.AUTO)

lib = Library('simplelib', sources=sources, includes=includes, library_type=self.options.library_type)
exe = Executable('pymake-simple-lib', sources=['main.cpp'], dependencies=[lib])

self.install(exe, lib)
