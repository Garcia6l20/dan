import platform
from typing import Any
from pymake.core.pm import re_match
from pymake.core.runners import async_run
from pymake.core.target import Target
from pymake.core import aiofiles
import jinja2

_conanfile_template = """[requires]
{% for r in requirements %}
{{r.name}}/{{r.version}}
{%- endfor %}

[options]
{% for r in requirements -%}
{% for k, v in r.options.items() %}
{{r.name}}/*:{{k}}={{v}}
{%- endfor %}
{%- endfor %}

[generators]
PkgConfigDeps
"""


class ConanFile(Target):
    def __init__(self, makefile) -> None:
        super().__init__('conanfile', makefile=makefile)
        self.__reqs = list()
        self.output = self.build_path / 'conanfile.txt'

    def add(self, pkg: 'Package'):
        self.__reqs.append(pkg)

    async def __build__(self):
        template = jinja2.Environment(
            loader=jinja2.BaseLoader).from_string(_conanfile_template)
        content = template.render(requirements=self.__reqs)
        async with aiofiles.open(self.output, 'w') as out:
            await out.write(content)


class Requirements(Target):

    def __init__(self, makefile) -> None:
        super().__init__('conan', makefile=makefile)

        self.output = self.makefile.parent.build_path / 'pkgs' / 'conanrun'
        if platform.system() == 'Windows':
            self.output = self.output.with_suffix('.bat')
        else:
            self.output = self.output.with_suffix('.sh')

        self.conanfile = ConanFile(makefile=makefile)
        self.preload_dependencies.add(self.conanfile)

    def _get_version(self, toolchain):
        from pymake.cxx.msvc_toolchain import MSVCToolchain
        match toolchain:
            case MSVCToolchain():
                return f'{toolchain.version.major}{str(toolchain.version.minor)[0]}'
            case _:
                return str(toolchain.version.major)
            
    def add(self, pkg: 'Package'):
        self.conanfile.add(pkg)

    async def __build__(self):
        from pymake.cxx import target_toolchain
        dest = self.output.parent
        dest.mkdir(exist_ok=True, parents=True)
        await async_run([
            'conan', 'install', '.',
            f'--output-folder={dest}',
            '-s', f'build_type={target_toolchain.build_type.name.title()}',
            '-s', f'compiler={target_toolchain.type}',
            '-s', f'compiler.version={self._get_version(target_toolchain)}',
            '-s', f'compiler.cppstd={target_toolchain.cpp_std}',
            '--build=missing'],
            logger=self._logger, cwd=self.build_path)

class Package(Target):
    def __get_requirements(self) -> Requirements:
        if not hasattr(self.makefile, '__conan_requirements__'):
            setattr(self.makefile, '__conan_requirements__', Requirements(makefile=self.makefile))
        return getattr(self.makefile, '__conan_requirements__')

    def __init__(self):
        super().__init__()
        # assert self.parent is not None
        reqs = self.__get_requirements()
        reqs.add(self)
        self.output = reqs.output.parent / f'{self.name}.pc'
        self.dependencies.add(reqs)
