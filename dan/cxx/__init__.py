import sys
from dan.core.cache import Cache

from dan.core.errors import InvalidConfiguration
from dan.core.settings import Settings
from dan.cxx.toolchain import Toolchain, BuildType, CppStd
from dan.cxx.detect import get_toolchains

target_toolchain: Toolchain = None
"""The target toolchain.
"""

host_toolchain: Toolchain = None
"""The host toolchain.
"""

class __LazyContext(sys.__class__):
    """Base class for the cxx module.

    It overloads some context dependent properties exposed by this module, eg.: target and host toolchains.
    """
    @property
    def target_toolchain(__) -> Toolchain:
        from dan.core.include import context
        return context.get('cxx_target_toolchain')

    @property
    def host_toolchain(__) -> Toolchain:
        from dan.core.include import context
        return context.get('cxx_host_toolchain')
    

sys.modules[__name__].__class__ = __LazyContext


auto_fpic = True

def get_default_toolchain(data = None):
    data = data or get_toolchains()
    return data['default']


def init_toolchains(name: str = None, settings: Settings = None):
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
    target_settings = settings.target
    cache = Cache.get('dan').data
    if not 'toolchains' in cache:
        cache['toolchains'] = {
            'host': dict(),
            'target': dict(),
        }
    target_toolchain = tc_type(toolchain_data, data['tools'], settings=target_settings, cache=cache['toolchains']['target'])
    target_toolchain.init()
    if target_toolchain.is_host:
        host_toolchain = target_toolchain
    else:
        from dan import logging
        logging.getLogger('cxx').warning('Cross compilation is currently not tested !')
        host_toolchain = None

    from dan.core.include import context
    context.set('cxx_target_toolchain', target_toolchain)
    context.set('cxx_host_toolchain', host_toolchain)


from .targets import Executable, Library, LibraryType, Module
from .targets import CXXObjectsTarget as Objects
