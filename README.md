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


## Cli usage:

### Toolchain scan

```bash
pymake scan-toolchains [-s <env-script>]
```

### Configuration

```bash
pymake configure [-B <build_path>] [-S <source_path>] [-t <toolchain>] [-s <setting>=<value>] [-o <option>=<value>]
```

### Build

```bash
pymake build [-B <build_path>] [-v] [--for-install] [TARGETS]...
```

### Install

Install targets marked with `self.install(...)` to the *install.destination* setting.

```bash
pymake install [-B <build_path>] [TARGETS]... [user|dev]
```

Settings:
- *install.destination*: The install destination (default: /usr/local).
- *install.runtime_prefix*: Executables installation prefix (default: bin).
- *install.libraries_prefix*: Libraries installation prefix (default: lib).
- *install.includes_prefix*: Includes installation prefix (default: include).
- *install.data_prefix*: Data files installation prefix (default: share).
- *install.project_prefix*: !!! NOT USED YET !!! Project prefix (default: None).
