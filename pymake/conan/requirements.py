import platform
from pymake.core.pm import re_match
from pymake.core.runners import async_run
from pymake.core.target import Target
from pymake.core import aiofiles
import jinja2

_conanfile_template = """[requires]
{% for r in requirements %}
{{r.name}}/{{r.refspec}}
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
    @staticmethod
    def from_spec(spec: str, parent=None):
        match re_match(spec):
            case r'(.+)/(.+)' as m:
                return Package(name=m[1], refspec=m[2], parent=parent)
            case _:
                raise RuntimeError(f'invalid conan requirement specification "{spec}"')

    def __init__(self, name, refspec, options:dict[str, bool|str] = dict(), parent=None) -> None:
        super().__init__(name, version=refspec, parent=parent)
        self.refspec = refspec
        self.options = options
        self.makefile.export(self)
    
    def __initialize__(self):
        assert self.parent is not None
        self.output = self.parent.output.parent / f'{self.name}.pc'
        self.load_dependency(self.parent)


class Requirements(Target):

    def __init__(self, *requirements) -> None:
        super().__init__('conan', 'conan requirements')

        self.output = self.makefile.parent.build_path / 'pkgs' / 'conanrun'
        if platform.system() == 'Windows':
            self.output = self.output.with_suffix('.bat')
        else:
            self.output = self.output.with_suffix('.sh')

        reqs = list()
        for r in requirements:
            match r:
                case str():
                    reqs.append(Package.from_spec(r, parent=self))
                case Package():
                    r.parent = self
                    reqs.append(r)
                case _:
                    raise RuntimeError(f'unhandled requirement specification "{r}" (type: "{type(r)}")')
        self.preload_dependencies.add(ConanFile(reqs))

        
    async def __build__(self):
        from pymake.cxx import target_toolchain
        dest = self.output.parent
        dest.mkdir(exist_ok=True, parents=True)
        await async_run(f'conan install . --output-folder={dest} -s build_type={target_toolchain.build_type.name.title()} -s compiler={target_toolchain.type} -s compiler.cppstd={target_toolchain.cpp_std} --build=missing', logger=self._logger, cwd=self.build_path)
