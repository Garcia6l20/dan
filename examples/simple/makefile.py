#!/usr/bin/env python3

from pymake import generator
from pymake.jinja import generator as jgenerator

import aiofiles

#
# sync generator definition with source dependency
#
@jgenerator('hello.txt', 'source.jinja')
def hello():
    return {'data': 'hello !!'}

#
# async generator definition with target dependency
#
@generator('hello-cpy.txt', dependencies=[hello])
async def hello_cpy(self):
    assert hello.up_to_date
    async with aiofiles.open(hello.output, 'r') as input:
        async with aiofiles.open(self.output, 'w') as output:
            await output.write(await input.read())
