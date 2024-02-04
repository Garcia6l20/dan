from dan.core.settings import BuildSettings as Settings, BuildType
from dan.core.toolchains import BaseToolchain
from dan.core.register import Registry

import typing as t

class ConfigContext(Registry, registry=True):

    name: str = None

    def __init__(self):
        self.accepted_toolchains: list[tuple[BaseToolchain, t.Any]] = list()

    def try_configure(self, toolchain: BaseToolchain, settings: t.Any) -> bool:
        return True


def use(*context_classes: type[ConfigContext]):
    for context_class in context_classes:
        ConfigContext.register(context_class)


class DefaultContext(ConfigContext, internal=True):
    name = 'default'


class OptimizedConfig(ConfigContext, internal=True):
    name = 'optimized'

    def try_configure(self, toolchain: BaseToolchain, settings: t.Any) -> bool:
        settings.build_type = BuildType.release
        return True

class DebugConfig(ConfigContext, internal=True):
    name = 'debug'

    def try_configure(self, toolchain: BaseToolchain, settings: t.Any) -> bool:
        settings.build_type = BuildType.release
        return True
