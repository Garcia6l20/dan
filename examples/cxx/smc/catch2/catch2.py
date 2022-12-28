import os
import shutil
from pymake import self
from pymake.cxx import Library, target_toolchain
from pymake.smc import GitSources
from pymake.cmake import ConfigureFile

version = '3.2.1'
description = 'A modern, C++-native, test framework for unit-tests, TDD and BDD'

git = GitSources(
    'git-catch2', 'https://github.com/catchorg/Catch2.git', f'v{version}')

src = git.output / 'src'

config = ConfigureFile('catch2.config', src / 'catch2/catch_user_config.hpp.in',
                       output_file=self.build_path / 'generated/catch2/catch_user_config.hpp',
                       dependencies=[git])

catch2 = Library('catch2',
                 description=description,
                 version=version,
                 sources=lambda: src.rglob('*.cpp'),
                 includes=[src, self.build_path / 'generated'],
                 preload_dependencies=[config],
                 all=False)

config.options = catch2.options


def add_overridable_catch2_option(name: str, value: bool):
    o = catch2.options.add(name, value)
    config[f'CATCH_CONFIG_{name.upper()}'] = o.value
    config[f'CATCH_CONFIG_NO_{name.upper()}'] = not o.value


def add_catch2_option(name: str, value):
    o = catch2.options.add(name, value)
    config[f'CATCH_CONFIG_{name.upper()}'] = o.value


add_overridable_catch2_option('counter', True)
add_overridable_catch2_option('android_logwrite', False)
add_overridable_catch2_option('colour_win32', os.name == 'nt')
add_overridable_catch2_option(
    'cpp11_to_string', target_toolchain.cpp_std >= 11)
add_overridable_catch2_option('cpp17_byte', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('cpp17_optional', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option(
    'cpp17_string_view', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option(
    'cpp17_uncaught_exceptions', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('cpp17_variant', target_toolchain.cpp_std >= 17)
add_overridable_catch2_option('global_nextafter', True)
add_overridable_catch2_option('posix_signals', os.name == 'posix')
add_overridable_catch2_option('getenv', True)
add_overridable_catch2_option('use_async', True)
# add_overridable_catch2_option('WCHAR', False)
add_overridable_catch2_option('windows_seh', os.name == 'nt')

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

@catch2.utility
def discover_tests(exe):
    from pymake import self as makefile
    import yaml
    output = exe.build_path / f'{exe.name}-tests.yaml'
    filepath = exe.source_path / exe.sources[0]
    if not output.exists() or output.older_than(filepath):
        import re
        test_macros = [
            'TEST_CASE',
            'SCENARIO'
        ]
        expr = re.compile(
            fr"({'|'.join(test_macros)})\(\s?\"([\w\s]+)\"[\s,]{{0,}}(?:\"(.+)\")?\)")  # (,.+)?\)"
        tests = dict()
        with open(filepath, 'r') as f:
            content = f.read()
            prev_pos = 0
            lineno = 0
            for m in expr.finditer(content):
                title = m.group(2)
                pos = m.span()[0]
                lineno = content.count('\n', prev_pos, pos) + lineno
                prev_pos = pos
                tests[title] = {
                    'filepath': str(filepath),
                    'lineno': lineno,
                }
                tags = m.group(3)
                if tags:
                    tests[title]['tags'] = tags

        with open(output, 'w') as f:
            f.write(yaml.dump(tests))

    with open(output, 'r') as f:
        tests: dict = yaml.load(f.read(), yaml.Loader)
        for title, data in tests.items():
            makefile.add_test(exe, name=title, args=[
                              title], file=data['filepath'], lineno=data['lineno'])

self.install(catch2)
