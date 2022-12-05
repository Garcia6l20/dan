from pymake.core.logging import Logging
from .toolchain import Toolchain, Path, FileDependency

import asyncio.subprocess

import sys


class AsyncRunner:
    async def run(self, command):
        self.debug(f'executing: {command}')
        proc = await asyncio.subprocess.create_subprocess_shell(command,
                                                                stdout=asyncio.subprocess.PIPE,
                                                                stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        if proc.returncode != 0:
            self.error(f'running command: {command}\n{err.decode()}')
            sys.exit(-1)
        return out, err


class GCCToolchain(Toolchain, AsyncRunner, Logging):
    def __init__(self, cc: Path = 'gcc', cxx: Path = 'g++'):
        super().__init__('gcc-toolchain')
        self.cc = cc
        self.cxx = cxx

    def make_include_options(self, include_paths: list[Path]) -> list[str]:
        return [f'-I{p}' for p in include_paths]

    async def scan_dependencies(self, file: Path, options: list[str]) -> list[FileDependency]:
        out, _ = await self.run(f'{self.cxx} -M {file} {" ".join(options)}')
        all = ''.join([dep.replace('\\', ' ')
                      for dep in out.decode().splitlines()]).split()
        _obj = all.pop(0)
        _src = all.pop(0)
        return [FileDependency(dep) for dep in all]

    async def compile(self, sourcefile: Path, output: Path, options: list[str]):
        await self.run(f'{self.cxx} -g -O -c {sourcefile} {" ".join(options)} -o {output}')

    async def link(self, objects: list[Path], output: Path, options: list[str]):
        await self.run(f'{self.cxx} -o {output} {" ".join(options)} {" ".join(objects)}')
