from pymake import target

import aiofiles
from jinja2 import Environment, FileSystemLoader


#
# sync target definition with source dependency
#
@target('hello.txt', dependencies='source.jinja')
def hello(self):
    env = Environment(loader=FileSystemLoader(self.source_path))
    template = env.get_template('source.jinja')
    print(template.render({'data': 'hello'}), file=open('hello.txt', 'w'))

#
# async target definition with target dependency
#
@target('hello-cpy.txt', dependencies=hello)
async def hello_cpy(self):
    assert hello.up_to_date
    async with aiofiles.open(hello.output, 'r') as input:
        async with aiofiles.open(self.output, 'w') as output:
            await output.write(await input.read())
