from dan.core.pathlib import Path
import re
from typing import Any
from dan.core.target import Target

import aiofiles


class ConfigureFile(Target, internal=True):

    input: Path = None
    variables: dict[str, Any] = dict()

    _cmake_define_expr = re.compile(r'#\s?cmakedefine\s+(\w+)\s?(@\w+@)?')
    _define_expr = re.compile(r'#\s?define\s+(\w+)\s+"?(@(\w+)@)"?')

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__variables = self.variables

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
        
        async with aiofiles.open(self.input, 'r') as inf, aiofiles.open(self.output, 'w') as outf:
            for line in await inf.readlines():                
                m = self._cmake_define_expr.search(line)
                if m:
                    line = gen_define(m.group(1), m.group(2))
                m = self._define_expr.search(line)
                if m:
                    line = gen_define(m.group(1), m.group(2))

                await outf.write(line)
