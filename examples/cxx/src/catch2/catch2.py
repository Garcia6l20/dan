from dan.src import GitSources
from dan.cmake import Project as CMakeProject
from dan.core import asyncio, aiofiles
from dan.cxx import BuildType

version = '3.2.1'
description = 'A modern, C++-native, test framework for unit-tests, TDD and BDD'


class Catch2Source(GitSources):
    name = 'catch2-source'
    url = 'https://github.com/catchorg/Catch2.git'
    refspec = f'v{version}'
    patches = 'patches/0001-fix-add-missing-cstdint-includes.patch',


class Catch2(CMakeProject):
    name = 'catch2'
    provides = ['catch2-with-main']
    preload_dependencies = [Catch2Source]
    cmake_options_prefix = 'CATCH'    

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_path = self.get_dependency(Catch2Source).output

    async def __install__(self, installer):
        await super().__install__(installer)
        if self.toolchain.build_type == BuildType.debug:
            # patch: no 'd' postfix in pkgconfig
            async with asyncio.TaskGroup() as g:
                g.create_task(aiofiles.replace_in_file(installer.settings.data_destination / 'pkgconfig' / 'catch2.pc',
                                              '-lCatch2', '-lCatch2d'))
                g.create_task(aiofiles.replace_in_file(installer.settings.data_destination / 'pkgconfig' / 'catch2-with-main.pc',
                                              '-lCatch2Main', '-lCatch2Maind'))


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
