import os
import shutil
from pymake import self
from pymake.cxx import Library, target_toolchain
from pymake.smc import GitSources
from pymake.cmake import ConfigureFile

git = GitSources(
    'git-catch2', 'https://github.com/catchorg/Catch2.git', 'v2.13.10')

src = git.output / 'src'

config = ConfigureFile('catch2.config', src / 'catch2/catch_user_config.hpp.in',
                       output_file=self.build_path / 'generated/catch2/catch_user_config.hpp',
                       dependencies=[git])

catch2 = Library('catch2',
                 sources=lambda: src.rglob('*.cpp'),
                 includes=[src, self.build_path / 'generated'],
                 preload_dependencies=[config],
                 all=False)

config.options = catch2.options


def add_overridable_catch2_option(name: str, value: bool):
    o = catch2.options.add(name.lower(), value)
    config[f'CATCH_CONFIG_{name}'] = o.value
    config[f'CATCH_CONFIG_NO_{name}'] = not o.value

def add_catch2_option(name: str, value):
    o = catch2.options.add(name.lower(), value)
    config[f'CATCH_CONFIG_{name}'] = o.value


add_overridable_catch2_option('COUNTER', True)
add_overridable_catch2_option('ANDROID_LOGWRITE', False)
add_overridable_catch2_option('COLOUR_WIN32', os.name == 'nt')
add_overridable_catch2_option(
    'CPP11_TO_STRING', target_toolchain.cpp_std >= 11)
add_overridable_catch2_option('CPP17_BYTE', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('CPP17_OPTIONAL', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option(
    'CPP17_STRING_VIEW', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option(
    'CPP17_UNCAUGHT_EXCEPTIONS', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('CPP17_VARIANT', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('GLOBAL_NEXTAFTER', True)
add_overridable_catch2_option('POSIX_SIGNALS', os.name == 'posix')
add_overridable_catch2_option('GETENV', True)
add_overridable_catch2_option('USE_ASYNC', True)
# add_overridable_catch2_option('WCHAR', False)
add_overridable_catch2_option('WINDOWS_SEH', os.name == 'nt')

add_catch2_option('bazel_support', False)
add_catch2_option('disable_exceptions', False)
add_catch2_option('disable', False)
add_catch2_option('disable_stringification', False)
add_catch2_option('all_stringmarkers', True)
add_catch2_option('optional_stringmaker', True)
add_catch2_option('pair_stringmaker', True)
add_catch2_option('tuple_stringmaker', True)
add_catch2_option('variant_stringmaker', False)
add_catch2_option('experimental_redirect', False)
add_catch2_option('fast_compile', False)
add_catch2_option('prefix_all', False)
add_catch2_option('windows_crtdbg', os.name == 'nt')
add_catch2_option('experimental_redirect', False)
add_catch2_option('default_reporter', 'console')
add_catch2_option('console_width', shutil.get_terminal_size().columns)

# config['CATCH_CONFIG_FALLBACK_STRINGIFIER'] = "fallback ??"

self.export(catch2)
