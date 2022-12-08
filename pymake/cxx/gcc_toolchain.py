import asyncio
from pymake.logging import Logging
from pymake.core.utils import AsyncRunner
from pymake.cxx.toolchain import Toolchain, Path, FileDependency, scan
from pymake.core.errors import InvalidConfiguration


class GCCToolchain(Toolchain, AsyncRunner, Logging):
    def __init__(self, cc: Path = 'gcc', cxx: Path = 'g++'):
        Toolchain.__init__(self)
        Logging.__init__(self, 'gcc-toolchain')
        self.cc = cc
        self.cxx = cxx
        self.ar = f'{cc}-ar'
        self.ranlib = f'{cc}-ranlib'

    def set_mode(self, mode: str):
        self.default_flags = set()
        if mode == 'debug':
            self.default_flags.update(('-g', ))
        elif mode == 'release':
            self.default_flags.update(('-O3', '-DNDEBUG'))
        elif mode == 'release-min-size':
            self.default_flags.update(('-Os', '-DNDEBUG'))
        elif mode == 'release-debug-infos':
            self.default_flags.update(('-O2', '-g', '-DNDEBUG'))
        else:
            raise InvalidConfiguration(f'unknown build mode: {mode}')

    def has_cxx_compile_options(self, *opts) -> bool:
        _, err, _ = asyncio.run(
            self.run(f'{self.cxx} {" ".join(opts)}', no_raise=True))
        return err.splitlines()[0].find('no input files') >= 0

    def make_include_options(self, include_paths: set[Path]) -> set[str]:
        return {f'-I{p}' for p in include_paths}

    def make_link_options(self, libraries: set[Path | str]) -> set[str]:
        opts = set()
        for lib in libraries:
            if isinstance(lib, Path):
                opts.add(f'-L{lib.parent}')
                opts.add(f'-Wl,-rpath,{lib.parent}')
                opts.add(f'-l{lib.stem.removeprefix("lib")}')
            else:
                assert isinstance(lib, str)
                opts.add(f'-l{lib}')
        return opts

    def make_compile_definitions(self, definitions: set[str]) -> set[str]:
        return {f'-D{d}' for d in definitions}

    async def scan_dependencies(self, file: Path, options: set[str]) -> set[FileDependency]:
        if not scan:
            return set()

        out, _, _ = await self.run(f'{self.cxx} -M {file} {" ".join(options)}')
        all = ''.join([dep.replace('\\', ' ')
                      for dep in out.splitlines()]).split()
        _obj = all.pop(0)
        _src = all.pop(0)
        return {FileDependency(dep) for dep in all}

    def compile_generated_files(self, output: Path) -> set[Path]:
        return {output.with_suffix(output.suffix + '.d')}

    @property
    def cxxmodules_flags(self) -> set[str]:
        return {'-std=c++20', '-fmodules-ts'}

    async def compile(self, sourcefile: Path, output: Path, options: set[str]):
        args = [*self.default_flags, *options, '-MD', '-MT',
                str(output), '-MF', f'{output}.d', '-o', str(output), '-c', str(sourcefile)]
        command = f'{self.cxx} {" ".join(args)}'
        self.compile_commands.insert(sourcefile, output.parent, command)
        await self.run(command)

    async def link(self, objects: set[Path], output: Path, options: set[str]):
        await self.run(f'{self.cxx} {" ".join(objects)} -o {output} {" ".join(options)}')

    async def static_lib(self, objects: set[Path], output: Path, options: set[str] = set()):
        await self.run(f'{self.ar} qc {output} {" ".join(options)} {" ".join(objects)}')
        await self.run(f'{self.ranlib} {output}')

    async def shared_lib(self, objects: set[Path], output: Path, options: set[str] = set()):
        await self.run(f'{self.cxx} -shared {" ".join(options)} {" ".join(objects)} -o {output}')
