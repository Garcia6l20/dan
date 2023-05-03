import os
import shutil
from pymake import self
from pymake.cxx import Library, target_toolchain
from pymake.smc import GitSources
from pymake.cmake import ConfigureFile

version = '3.2.1'
description = 'A modern, C++-native, test framework for unit-tests, TDD and BDD'


class Catch2Source(GitSources):
    name = 'catch2-source'
    url = 'https://github.com/catchorg/Catch2.git'
    refspec = f'v{version}'
    patches = 'patches/0001-fix-add-missing-cstdint-includes.patch',


class Config(ConfigureFile):
    name = 'catch2-config'
    dependencies = Catch2Source,
    output = 'generated/catch2/catch_user_config.hpp'

    async def __initialize__(self):
        await super().__initialize__()
        self.input = self.get_dependency(
            'catch2-source').output / 'src/catch2/catch_user_config.hpp.in'


class Catch2(Library):
    name = 'catch2'
    preload_dependencies = Config,

    def sources(self):
        return (self.get_dependency('catch2-source').output / 'src').rglob('*.cpp')

    async def __initialize__(self):

        src = self.get_dependency('catch2-source').output / 'src'
        self.config = self.get_dependency('catch2-config')
        self.config.options = self.options
        self.includes.add(src, public=True)
        self.includes.add(self.build_path / 'generated', public=True)
        if self.toolchain.type == 'msvc':
            self.link_options.add('/SUBSYSTEM:CONSOLE', public=True)

        self.add_overridable_catch2_option('counter', True)
        self.add_overridable_catch2_option('android_logwrite', False)
        self.add_overridable_catch2_option('colour_win32', os.name == 'nt')
        self.add_overridable_catch2_option(
            'cpp11_to_string', target_toolchain.cpp_std >= 11)
        self.add_overridable_catch2_option(
            'cpp17_byte', target_toolchain.cpp_std >= 17)
        self.add_overridable_catch2_option(
            'cpp17_optional', target_toolchain.cpp_std >= 17)
        self.add_overridable_catch2_option(
            'cpp17_string_view', target_toolchain.cpp_std >= 17)
        self.add_overridable_catch2_option(
            'cpp17_uncaught_exceptions', target_toolchain.cpp_std >= 17)
        self.add_overridable_catch2_option(
            'cpp17_variant', target_toolchain.cpp_std >= 17)
        self.add_overridable_catch2_option('global_nextafter', True)
        self.add_overridable_catch2_option('posix_signals', os.name == 'posix')
        self.add_overridable_catch2_option('getenv', True)
        self.add_overridable_catch2_option('use_async', True)
        # self.add_overridable_catch2_option('WCHAR', False)
        self.add_overridable_catch2_option('windows_seh', os.name == 'nt')

        self.add_catch2_option('bazel_support', False)
        self.add_catch2_option('disable_exceptions', False)
        self.add_catch2_option('disable', False)
        self.add_catch2_option('disable_stringification', False)
        self.add_catch2_option('all_stringmarkers', True)
        self.add_catch2_option('optional_stringmaker', True)
        self.add_catch2_option('pair_stringmaker', True)
        self.add_catch2_option('tuple_stringmaker', True)
        self.add_catch2_option('variant_stringmaker', False)
        self.add_catch2_option('experimental_redirect', False)
        self.add_catch2_option('fast_compile', False)
        self.add_catch2_option('prefix_all', False)
        self.add_catch2_option('windows_crtdbg', os.name == 'nt')
        self.add_catch2_option('experimental_redirect', False)
        self.add_catch2_option('default_reporter', 'console')
        self.add_catch2_option(
            'console_width', shutil.get_terminal_size().columns)

        await super().__initialize__()

    def add_overridable_catch2_option(self, name: str, value: bool):
        o = self.options.add(name, value)
        self.config[f'CATCH_CONFIG_{name.upper()}'] = o.value
        self.config[f'CATCH_CONFIG_NO_{name.upper()}'] = not o.value

    def add_catch2_option(self, name: str, value):
        o = self.options.add(name, value)
        self.config[f'CATCH_CONFIG_{name.upper()}'] = o.value

# FIXME: this is actually associated to Target's utils


@Catch2.utility
def discover_tests(self, exe):
    from pymake import self as makefile
    from pymake.cxx import Executable
    if not issubclass(exe, Executable):
        raise RuntimeError(
            f'catch2.discover_tests requires an Executable class, not a {exe.__name__}')
    import yaml
    exe: Executable = exe(makefile=makefile)
    output = exe.build_path / f'{exe.name}-tests.yaml'
    filepath = exe.source_path / exe.sources[0]
    if not output.exists() or output.older_than(filepath):
        import re
        test_macros = [
            'TEST_CASE',
            'SCENARIO',
            'TEMPLATE_TEST_CASE'
        ]
        expr = re.compile(
            fr"({'|'.join(test_macros)})\(\s?\"(.*?)\"[\s,]{{0,}}(?:\"(.*?)\")?")
        tests = dict()

        def is_commented(pos: int, content: str):
            linestart = content.rfind('\n', 0, pos)
            if linestart != -1 and content.find('//', linestart + 1, pos) != -1:
                return True
            blockstart = content.rfind('/*', 0, pos)
            if blockstart != -1 and content.find('*/', blockstart + 2, pos) == -1:
                return True
            return False

        with open(filepath, 'r') as f:
            content = f.read()
            prev_pos = 0
            lineno = 0
            for m in expr.finditer(content):
                pos = m.span()[0]
                if is_commented(pos, content):
                    continue

                macro = m.group(1)
                title = m.group(2)
                if macro == 'SCENARIO':
                    title = 'Scenario: ' + title
                lineno = content.count('\n', prev_pos, pos) + lineno
                prev_pos = pos
                tags = m.group(3)
                if macro == 'TEMPLATE_TEST_CASE':
                    targs_start = m.span()[1] + 1
                    targs_end = content.find(')', targs_start)
                    targs = content[targs_start:targs_end]
                    targs = [a.strip() for a in targs.split(',')]
                    for targ in targs:
                        tests[f'{title} - {targ}'] = {
                            'filepath': str(filepath),
                            'lineno': lineno,
                        }
                else:
                    tests[title] = {
                        'filepath': str(filepath),
                        'lineno': lineno,
                    }
                    if tags:
                        tests[title]['tags'] = tags

        with open(output, 'w') as f:
            f.write(yaml.dump(tests))

    with open(output, 'r') as f:
        from pymake.testing import Test
        tests: dict = yaml.load(f.read(), yaml.Loader)
        for title, data in tests.items():
            class Catch2Test(Test):
                name = title
                executable = exe
                file = data['filepath']
                lineno = data['lineno']
                cases = [((title, ), 0),]
            makefile.register(Catch2Test)
