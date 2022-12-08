import logging

from pymake.core.errors import InvalidConfiguration
from .toolchain import Toolchain

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None

auto_fpic = True

def init_toolchains(name):
    from .detect import get_toolchains
    data = get_toolchains()
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

def __init_toolchains():
    import os
    import sys
    tid = os.getenv('PYMAKE_TOOLCHAIN', None)
    if not tid:
        index = sys.argv.index('-t')
        if index < 0:
            index = sys.argv.index('--toolchain')
        if index < 0:
            tid = 'default'
        else:
            tid = sys.argv[index + 1]
    init_toolchains(tid)

__init_toolchains()

from .targets import Executable, Library, Module
from .targets import CXXObjectsTarget as Objects
