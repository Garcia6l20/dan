import sys

from pymake.core.errors import InvalidConfiguration
from pymake.cxx.toolchain import Toolchain
from pymake.cxx.detect import get_toolchains

target_toolchain: Toolchain = None
host_toolchain: Toolchain = None

class __LazyContext(sys.__class__):
    @property
    def target_toolchain(__):
        from pymake.core.include import context
        return context.get('cxx_target_toolchain')

    @property
    def host_toolchain(__):
        from pymake.core.include import context
        return context.get('cxx_host_toolchain')
    

sys.modules[__name__].__class__ = __LazyContext


auto_fpic = True

def get_default_toolchain(data = None):
    data = data or get_toolchains()
    return data['default']


def init_toolchains(name: str = None):
    data = get_toolchains()
    if name is None or name == 'default':
        name = get_default_toolchain(data)

    toolchain_data = data['toolchains'][name]

    tc_type = toolchain_data['type']
    match tc_type:
        case 'gcc' | 'clang':
            from .unix_toolchain import UnixToolchain
            tc_type = UnixToolchain
        case 'msvc':
            from .msvc_toolchain import MSVCToolchain
            tc_type = MSVCToolchain
        case _:
            raise InvalidConfiguration(f'Unhandeld toolchain type: {tc_type}')
    target_toolchain = tc_type(toolchain_data, data['tools'])
    host_toolchain = target_toolchain

    from pymake.core.include import context
    context.set('cxx_target_toolchain', target_toolchain)
    context.set('cxx_host_toolchain', host_toolchain)

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

from .targets import Executable, Library, LibraryType, Module
from .targets import CXXObjectsTarget as Objects
