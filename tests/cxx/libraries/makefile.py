import os
from pymake.cxx import Library, Executable, Objects, target_toolchain

target_toolchain.cpp_std = 17

if os.name != 'nt':
    objects = Objects(sources=['lib.cpp'],
                    includes=['.'])

    static = Library(dependencies=[objects])

    shared = Library(static=False,
                    dependencies=[objects])

    statically_linked = Executable(sources=['main.cpp'], dependencies=[static])
    shared_linked = Executable(sources=['main.cpp'], dependencies=[shared])
else:
    # On windows we cannot share object-library
    # since object compilations need different definition (ie.: LIB_IMPORTS/LIB_EXPORTS)

    static = Library(sources=['lib.cpp'], includes=['.'])
    statically_linked = Executable(sources=['main.cpp'], dependencies=[static])

    shared = Library(sources=['lib.cpp'], includes=['.'], static=False)
    shared_linked = Executable(sources=['main.cpp'], dependencies=[shared])
