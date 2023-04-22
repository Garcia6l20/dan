import platform
from pymake.core.pm import re_match
from pymake.core.runners import async_run
from pymake.core.target import Target
from pymake.core import aiofiles
import jinja2

_conanfile_template = """[requires]
{% for r in requirements -%}
{{r.name}}/{{r.refspec}}
{%- endfor %}

[generators]
PkgConfigDeps
"""

class ConanFile(Target):
    def __init__(self, reqs: 'Requirements') -> None:
        super().__init__('conanfile', 'conan file generator')
        self.__reqs = reqs
        self.output = self.build_path / 'conanfile.txt'        

    async def __build__(self):
        template = jinja2.Environment(loader=jinja2.BaseLoader).from_string(_conanfile_template)
        content = template.render(requirements=self.__reqs)
        async with aiofiles.open(self.output, 'w') as out:
            await out.write(content)

class Package(Target):
    def __init__(self, spec, parent) -> None:
        match re_match(spec):
            case r'(.+)/(.+)' as m:
                self.refspec = m[2]
                super().__init__(name=m[1], version=self.refspec)
            case _:
                raise RuntimeError(f'invalid conan requirement specification "{spec}"')
                
        self.output = parent.output.parent / f'{self.name}.pc'
        self.makefile.export(self)
        self.load_dependency(parent)

class Requirements(Target):

    def __init__(self, *requirements) -> None:
        super().__init__('conan', 'conan requirements')

        self.output = self.makefile.parent.build_path / 'pkgs' / 'conanrun'
        if platform.system() == 'Windows':
            self.output = self.output.with_suffix('.bat')
        else:
            self.output = self.output.with_suffix('.sh')

        reqs = list()
        for spec in requirements:
            reqs.append(Package(spec, parent=self))
        self.preload_dependencies.add(ConanFile(reqs))

        
    async def __build__(self):
        from pymake.cxx import target_toolchain
        dest = self.output.parent
        dest.mkdir(exist_ok=True, parents=True)
        await async_run(f'conan install . --output-folder={dest} -s build_type={target_toolchain.build_type.name.title()} -s compiler={target_toolchain.type} -s compiler.cppstd={target_toolchain.cpp_std} --build=missing', logger=self._logger, cwd=self.build_path)
