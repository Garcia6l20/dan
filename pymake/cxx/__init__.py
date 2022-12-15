import logging

from pymake.core.errors import InvalidConfiguration
from pymake.cxx.toolchain import Toolchain
from pymake.cxx.detect import get_toolchains

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None

auto_fpic = True

def get_default_toolchain(data = None):
    data = data or get_toolchains()
    return data['default']
    


def init_toolchains(name: str = None):
    data = get_toolchains()
    if name is None or name == 'default':
        name = get_default_toolchain(data)

    toolchain_data = data['toolchains'][name]

    global target_toolchain, host_toolchain
    tc_type = toolchain_data['type']
    if tc_type == 'gcc':
        from .gcc_toolchain import GCCToolchain
        tc_type = GCCToolchain
    elif tc_type == 'msvc':
        from .msvc_toolchain import MSVCToolchain
        tc_type = MSVCToolchain
    else:
        raise InvalidConfiguration(f'Unhandeld toolchain type: {tc_type}')
    if target_toolchain is None: 
        target_toolchain = tc_type(toolchain_data, data['tools'])
    if host_toolchain is None:
        host_toolchain = target_toolchain

def __pick_arg(*names, env=None, default=None):
    import sys
    import os
    if env:
        value = os.getenv(env, None)
        if value:
            return value
    for name in names:
        try:
            return sys.argv[sys.argv.index(name) + 1]
        except ValueError:
            continue
    return default

#def __init_toolchains():
#    init_toolchains(__pick_arg('-t', '--toolchain', env='PYMAKE_TOOLCHAIN'))

#__init_toolchains()

from .targets import Executable, Library, Module
from .targets import CXXObjectsTarget as Objects
