#!/usr/bin/env python3

from pymake import cli, generator

import aiofiles
from jinja2 import Environment, FileSystemLoader


#
# sync generator definition with source dependency
#
@generator('hello.txt', dependencies='source.jinja')
def hello(self):
    env = Environment(loader=FileSystemLoader(self.source_path))
    template = env.get_template('source.jinja')
    print(template.render({'data': 'hello'}), file=open(self.output, 'w'))

#
# async generator definition with target dependency
#
@generator('hello-cpy.txt', dependencies=hello)
async def hello_cpy(self):
    assert hello.up_to_date
    async with aiofiles.open(hello.output, 'r') as input:
        async with aiofiles.open(self.output, 'w') as output:
            await output.write(await input.read())

if __name__ == '__main__':
    cli()
