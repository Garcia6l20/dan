import os
from dan.core.pm import re_match
from dan.cxx import Library, target_toolchain
from dan.src import GitSources
from dan.cmake import ConfigureFile

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
        self.add_catch2_option('console_width', 80)

    def add_overridable_catch2_option(self, name: str, value: bool):
        o = self.options.add(name, value)
        self[f'CATCH_CONFIG_{name.upper()}'] = o.value
        self[f'CATCH_CONFIG_NO_{name.upper()}'] = not o.value

    def add_catch2_option(self, name: str, value):
        o = self.options.add(name, value)
        self[f'CATCH_CONFIG_{name.upper()}'] = o.value

class Catch2(Library):
    name = 'catch2'
    preload_dependencies = Config,

    def sources(self):
        return (self.get_dependency('catch2-source').output / 'src').rglob('*.cpp')

    async def __initialize__(self):
        src = self.get_dependency('catch2-source').output / 'src'
        self.config = self.get_dependency('catch2-config')
        self.options = self.config.options
        self.includes.add(src, public=True)
        self.includes.add(self.build_path / 'generated', public=True)
        if self.toolchain.type == 'msvc':
            self.link_options.add('/SUBSYSTEM:CONSOLE', public=True)

        await super().__initialize__()


@Catch2.utility
def discover_tests(self, ExecutableClass):
    from dan.cxx import Executable
    from dan.core.pm import re_match

    if not issubclass(ExecutableClass, Executable):
        raise RuntimeError(
            f'catch2.discover_tests requires an Executable class, not a {ExecutableClass.__name__}')

    makefile = ExecutableClass.get_static_makefile()

    from dan.testing import Test, Case
    @makefile.wraps(ExecutableClass)
    class Catch2Test(Test, ExecutableClass):
        name = ExecutableClass.name or ExecutableClass.__name__

        def __init__(self, *args, **kwargs):
            Test.__init__(self, *args, **kwargs)
            ExecutableClass.__init__(self, *args, **kwargs)
            cases = self.cache.get('cases')
            if cases is not None:
                self.cases = cases
                self._up_to_date = True
            else:
                self._up_to_date = False
        
        @property
        def up_to_date(self):
            return self._up_to_date and super().up_to_date

        async def __build__(self):
            await super().__build__()
            if self.output.exists():
                out, err, rc = await self.execute('--list-tests', no_raise=True, log=False, build=False)
                self.cases = list()
                filepath = self.source_path / self.sources[0]
                for line in out.splitlines():
                    match re_match(line):
                        case r'  (\w.+)$' as m:
                            self.cases.append(Case(m[1], m[1], file=filepath))
                # search lineno
                from dan.core import aiofiles
                async with aiofiles.open(filepath, 'r') as f:
                    for lineno, line in enumerate(await f.readlines(), 1):
                        match re_match(line):
                            case r"(TEST_CASE|SCENARIO|TEMPLATE_TEST_CASE)\(\s?\"(.*?)\".+" as m:
                                # macro = m[1]
                                name = m[2]
                                for case in self.cases:
                                    if case.name == name:
                                        case.lineno = lineno
                                        break
                self.debug('test cases found: %s', ', '.join([c.name for c in self.cases]))
                self.cache['cases'] = self.cases
    return Catch2Test
