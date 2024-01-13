import sys
from dan.core.cache import Cache

from dan.core.errors import InvalidConfiguration
from dan.core.settings import BuildSettings
from dan.cxx.toolchain import Toolchain, BuildType, CppStd
from dan.cxx.detect import get_toolchains

toolchain: Toolchain = None
"""Current CXX toolchain.
"""


class __LazyContext(sys.__class__):
    """Base class for the cxx module.

    It overloads some context dependent properties exposed by this module, eg.: target and host toolchains.
    """
    @property
    def toolchain(__) -> Toolchain:
        from dan.core.include import context
        return context.get('cxx_toolchain')


sys.modules[__name__].__class__ = __LazyContext


auto_fpic = True

def get_default_toolchain(data = None):
    data = data or get_toolchains()
    return data['default']


def init_toolchain(ctx):
    data = get_toolchains()
    settings : BuildSettings = ctx.settings
    tc_name = settings.toolchain
    if tc_name is None or tc_name == 'default':
        tc_name = get_default_toolchain(data)

    toolchain_data = data['toolchains'][tc_name]

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
    
    cache = Cache.get('dan').data
    if not ctx.name in cache:
        cache[ctx.name] = {
            'toolchain': dict()
        }
    toolchain = tc_type(toolchain_data, data['tools'], settings=settings.cxx, cache=cache[ctx.name]['toolchain'])
    toolchain.init()
    ctx.set('cxx_toolchain', toolchain)


from .targets import Executable, Library, LibraryType, Module
from .targets import CXXObjectsTarget as Objects
