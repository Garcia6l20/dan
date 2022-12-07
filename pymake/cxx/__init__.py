from .toolchain import Toolchain

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None


def __init_toolchains():
    from .gcc_toolchain import GCCToolchain
    global target_toolchain, host_toolchain
    if target_toolchain is None:
        target_toolchain = GCCToolchain()
    if host_toolchain is None:
        host_toolchain = GCCToolchain()


__init_toolchains()


from .targets import Executable, Library, Module
from .targets import CXXObjectsTarget as Objects
