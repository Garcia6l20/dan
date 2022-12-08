import logging

from pymake.core.errors import InvalidConfiguration
from .toolchain import Toolchain

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None

toolchain_id = None
auto_fpic = True

def __init_toolchains():
    global toolchain_id
    from .detect import get_toolchains
    data = get_toolchains()
    if toolchain_id is None:
        toolchain_id = data['default']
    toolchain_data = data['toolchains'][toolchain_id]
        
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


__init_toolchains()


from .targets import Executable, Library, Module
from .targets import CXXObjectsTarget as Objects
