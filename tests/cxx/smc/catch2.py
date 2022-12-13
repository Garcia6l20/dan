import os
import shutil
from pymake import self
from pymake.cxx import Library, target_toolchain
from pymake.smc import GitSources
from pymake.cmake import ConfigureFile

git = GitSources(
    'git-catch2', 'https://github.com/catchorg/Catch2.git', 'v2.13.10')

src = git.output / 'src'

config = ConfigureFile(src / 'catch2/catch_user_config.hpp.in',
                       output_file=self.build_path / 'generated/catch2/catch_user_config.hpp',
                       dependencies=[git])


def add_overridable_catch2_option(name, value):
    config[f'CATCH_CONFIG_{name}'] = value
    config[f'CATCH_CONFIG_NO_{name}'] = not value


add_overridable_catch2_option('ANDROID_LOGWRITE', False)
add_overridable_catch2_option('COLOUR_WIN32', os.name == 'nt')
add_overridable_catch2_option('COUNTER', True)
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

config['CATCH_CONFIG_BAZEL_SUPPORT'] = False
config['CATCH_CONFIG_DISABLE_EXCEPTIONS'] = False
config['CATCH_CONFIG_DISABLE_EXCEPTIONS_CUSTOM_HANDLER'] = False
config['CATCH_CONFIG_DISABLE'] = False
config['CATCH_CONFIG_DISABLE_STRINGIFICATION'] = False
config['CATCH_CONFIG_ENABLE_ALL_STRINGMAKERS'] = True
config['CATCH_CONFIG_ENABLE_OPTIONAL_STRINGMAKER'] = True
config['CATCH_CONFIG_ENABLE_PAIR_STRINGMAKER'] = True
config['CATCH_CONFIG_ENABLE_TUPLE_STRINGMAKER'] = True
config['CATCH_CONFIG_ENABLE_VARIANT_STRINGMAKER'] = True
config['CATCH_CONFIG_EXPERIMENTAL_REDIRECT'] = False
config['CATCH_CONFIG_FAST_COMPILE'] = False
config['CATCH_CONFIG_NOSTDOUT'] = False
config['CATCH_CONFIG_PREFIX_ALL'] = False
config['CATCH_CONFIG_WINDOWS_CRTDBG'] = os.name == 'nt'

config['CATCH_CONFIG_SHARED_LIBRARY'] = False
config['CATCH_CONFIG_DEFAULT_REPORTER'] = 'console'
config['CATCH_CONFIG_CONSOLE_WIDTH'] = shutil.get_terminal_size().columns

# config['CATCH_CONFIG_FALLBACK_STRINGIFIER'] = "fallback ??"

self.export(Library('catch2',
                    sources=lambda: src.rglob('*.cpp'),
                    includes=[src, self.build_path / 'generated'],
                    preload_dependencies=[config],
                    all=False))
