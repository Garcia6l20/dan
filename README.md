# dan

> _Do Anything Now_

_dan_ is a build system inspired from _GNU make_, _cmake_, _meson_, ... but only in python.

It is mostly designed to be easy to use, it comes with its [vscode extension](https://github.com/Garcia6l20/dan-vscode) available on the [marketplace](https://marketplace.visualstudio.com/items?itemName=garcia6l20.dan).

It also provide a packaging system called [dan.io](https://github.com/Garcia6l20/dan.io),
that will fetch and build 3rd party libraries.

## Install

_dan_ is available on pip:

```bash
pip install dan-build
```

## Features

### Generators

Generators are python functions that generates an output:

```python
from dan import generator

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

### C/CXX

#### Libraries/Executables

```python
from dan.cxx import Library, Executable
class MyLib(Library):
    name = 'my-lib'
    sources = ['src/my-lib.cpp']
    public_includes = ['include']

class MyExe(Executable):
    name = 'my-exe'
    sources = ['src/main.cpp']
    dependencies = [MyLib]

```

#### Packages

[dan.io](https://github.com/Garcia6l20/dan.io) is the main (default) package source repository (custom repositories are supported by editting _~/.dan/repositories.json_), documentation comming soon.

```python
class MyExe(Executable):
    name = 'my-exe'
    sources = ['src/main.cpp']
    dependencies = ['boost:headers@dan.io >= 1.82']
```

## `dan` cli usage

`dan` is the main executable to build your project, it can build, test, list targets/test, ...

```bash
dan --help
Usage: dan [OPTIONS] COMMAND [ARGS]...

Options:
  --version           Show the version and exit.
  -q, --quiet         Dont print informations (errors only)
  -v, --verbose       Pring debug informations
  -j, --jobs INTEGER  Maximum jobs
  --help              Show this message and exit.

Commands:
  build            Build targets
  clean            Clean generated stuff
  code             VS-Code specific commands
  configure        Configure dan project
  install          Install targets
  ls               Inspect stuff
  run              Run executable(s)
  scan-toolchains  Scan system toolchains
  test             Run tests
  uninstall        Uninstall previous installation
```

### Toolchain scan

```bash
dan scan-toolchains [-s <env-script>]
```

### Configuration

```bash
dan configure [-B <build_path>] [-S <source_path>] [-t <toolchain>] [-s <setting>=<value>] [-o <option>=<value>]
```

### Build

```bash
dan build [-B <build_path>] [-v] [--for-install] [TARGETS]...
```

### Install

Install targets marked with `install = True` property to the *install.destination* setting.

```bash
dan install [-B <build_path>] [TARGETS]... [user|dev]
```

Settings:
- *install.destination*: The install destination (default: /usr/local).
- *install.runtime_prefix*: Executables installation prefix (default: bin).
- *install.libraries_prefix*: Libraries installation prefix (default: lib).
- *install.includes_prefix*: Includes installation prefix (default: include).
- *install.data_prefix*: Data files installation prefix (default: share).
- *install.project_prefix*: !!! NOT USED YET !!! Project prefix (default: None).

## `dan-io` cli usage

`dan-io` is a secondary utility to interract with package management system.

```bash
$ dan-io --help 
Usage: dan-io [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  ls      Inspect stuff
  search  Search for NAME in repositories
```

```bash
$ dan-io ls --help
Usage: dan-io ls [OPTIONS] COMMAND [ARGS]...

  Inspect stuff

Options:
  --help  Show this message and exit.

Commands:
  libraries     List available libraries
  repositories  List available repositories
  versions      Get LIBRARY's available versions
```


## Auto completion

_bash_ and _zsh_ completions are currently supported:

- _bash_:
    ```bash
    for script in ~/.local/etc/bash_completion.d/*.sh; do
        source ${script}
    done
    ```

- _ksh_:
    ```ksh
    for script in ~/.local/etc/ksh_completion.d/*.sh; do
        source ${script}
    done
    ```
