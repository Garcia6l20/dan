from pymake.core.pathlib import Path
import re
from typing import Any
from pymake.core import asyncio
from pymake.core.target import Target

import aiofiles


class ConfigureFile(Target):

    _cmake_define_expr = re.compile(r'#\s?cmakedefine\s+(\w+)\s?(@\w+@)?')
    _define_expr = re.compile(r'#\s?define\s+(\w+)\s+"?(@(\w+)@)"?')

    def __init__(self,
                 name: str,
                 input_file: str | Path,
                 output_file: Path = None,
                 variables: dict[str, Any] = dict(),
                 dependencies: list = list(),
                 preload_dependencies: list = list()) -> None:
        self.input_file: Path = Path(input_file)
        super().__init__(name, all=False)
        if not self.input_file.is_absolute():
            self.input_file = self.source_path / input_file
        if output_file:
            output_file = Path(output_file)
            self.output = output_file if output_file.is_absolute() else self.build_path / output_file
        else:
            self.output = self.build_path / \
                '.'.join(self.input_file.name.split('.')[:-1])
        self.preload_dependencies = set(preload_dependencies)
        self.load_dependencies(dependencies)
        self.load_dependency(self.input_file)
        self.__variables = variables

    def __setitem__(self, key, value):
        self.__variables[key] = value

    async def __build__(self):
        self.output.parent.mkdir(exist_ok=True, parents=True)
        def gen_define(name, replacement):
            if name in self.__variables:
                if replacement is None:
                    return f'#define {name}\n' if self.__variables[
                        name] else f'/* #undef {name} */\n'
                else:
                    replacement = replacement[1:-1]
                    assert replacement in self.__variables, f'{replacement} is not defined'
                    replacement = self.__variables[replacement]
                    if isinstance(replacement, str):
                        replacement = f'"{replacement}"'
                    return f'#define {name} {replacement}\n'
            else:
                 return f'/* #undef {name} */\n'
        
        async with aiofiles.open(self.input_file, 'r') as inf, aiofiles.open(self.output, 'w') as outf:
            writes = list()
            for line in await inf.readlines():                
                m = self._cmake_define_expr.search(line)
                if m:
                    line = gen_define(m.group(1), m.group(2))
                m = self._define_expr.search(line)
                if m:
                    line = gen_define(m.group(1), m.group(2))

                writes.append(outf.write(line))
            await asyncio.gather(*writes)

