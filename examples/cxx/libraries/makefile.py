import os
from pymake.cxx import Library, Executable, Objects, target_toolchain

target_toolchain.cpp_std = 17

if os.name != 'nt':
    objects = Objects('objects', sources=['lib.cpp'],
                      includes=['.'])

    static = Library('static', library_type=Library.Type.STATIC,
                     dependencies=[objects])

    shared = Library('shared', library_type=Library.Type.SHARED,
                     dependencies=[objects])

    Executable('statically_linked', sources=['main.cpp'], dependencies=[static])
    Executable('shared_linked', sources=['main.cpp'], dependencies=[shared])
else:
    # On windows we cannot share object-library
    # since object compilations need different definition (ie.: LIB_IMPORTS/LIB_EXPORTS)

    static = Library('static', sources=['lib.cpp'], includes=['.'])
    statically_linked = Executable(sources=['main.cpp'], dependencies=[static])

    Library('shared', sources=['lib.cpp'], includes=['.'], static=False)
    Executable(sources=['main.cpp'], dependencies=[shared])
