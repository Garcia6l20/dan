# pymake
> Makefiles - in python

_pymake_ is a build system inspired from _GNU make_, _cmake_, _meson_, ... but only in python.

## Features

- Generators:

Generators are python functions that generates an output:
```python
@generator(output='hello.txt', dependencies=['source.jinja'])
def hello(self):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.source_path))
    template = env.get_template('source.jinja')
    print(template.render({'data': 'hello'}), file=open(self.output, 'w'))
```

They can be async:
```python
@generator(output='hello-cpy.txt', dependencies=[hello])
async def hello_cpy(self):
    assert hello.up_to_date
    async with aiofiles.open(hello.output, 'r') as src:
        async with aiofiles.open(self.output, 'w') as dst:
            await dst.write(await src.read())
```
