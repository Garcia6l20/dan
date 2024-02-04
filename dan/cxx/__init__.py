import sys
from dan.core.cache import Cache

from dan.core.errors import InvalidConfiguration
from dan.core.settings import BuildSettings
from dan.cxx.base_toolchain import Toolchain, BuildType, CppStd
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

    @property
    def target_toolchain(self) -> Toolchain:
        return self.toolchain


sys.modules[__name__].__class__ = __LazyContext


auto_fpic = True

def get_default_toolchain(data = None):
    data = data or get_toolchains()
    return data['default']

def get_toolchain_class(toolchain_data: dict):
    tc_id = toolchain_data['id']
    from .base_toolchain import Toolchain
    Toolchain.load_all()
    for cls in Toolchain.registered_classes(lambda t: t.final):
        if tc_id == cls.name:
            return cls


def get_toolchain_classes():
    data = get_toolchains()
    return [get_toolchain_class(toolchain_data) for toolchain_data in data['toolchains'].values()]

def init_toolchain(ctx):
    data = get_toolchains()
    settings : BuildSettings = ctx.settings
    tc_name = settings.toolchain
    if tc_name is None or tc_name == 'default':
        tc_name = get_default_toolchain(data)

    toolchain_data = data['toolchains'][tc_name]
    ToolchainClass = get_toolchain_class(toolchain_data)

    cache = Cache.get('dan').data
    if not ctx.name in cache:
        cache[ctx.name] = {
            'toolchain': dict()
        }
    toolchain = ToolchainClass(settings=settings.config, cache=cache[ctx.name]['toolchain'])
    toolchain.init()
    ctx.set('cxx_toolchain', toolchain)
    return toolchain


from .targets import Executable, Library, LibraryType, Module
from .targets import CXXObjectsTarget as Objects
