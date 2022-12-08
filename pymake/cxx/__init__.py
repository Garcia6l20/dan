import logging

from pymake.core.errors import InvalidConfiguration
from .toolchain import Toolchain

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None

auto_fpic = True

def init_toolchains(name):
    from .detect import get_toolchains
    data = get_toolchains()
    if name is None:
        name = data['default']
    toolchain_data = data['toolchains'][name]
        
    from .gcc_toolchain import GCCToolchain
    global target_toolchain, host_toolchain
    tc_type = toolchain_data['type']
    if tc_type == 'gcc':
        if target_toolchain is None: 
            target_toolchain = GCCToolchain(toolchain_data, data['tools'])
        if host_toolchain is None:
            target_toolchain = GCCToolchain(toolchain_data, data['tools'])
    else:
        raise InvalidConfiguration(f'Unhandeld toolchain type: {tc_type}')

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

def __init_toolchains():
    init_toolchains(__pick_arg('-t', '--toolchain', env='PYMAKE_TOOLCHAIN'))

__init_toolchains()

from .targets import Executable, Library, Module
from .targets import CXXObjectsTarget as Objects
