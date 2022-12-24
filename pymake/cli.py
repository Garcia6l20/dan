import os
import sys
from pymake.core.find import find_file
from pymake.core.pathlib import Path
import click

import logging
import asyncio
from pymake.core.cache import Cache
from pymake.core.settings import Settings
from pymake.cxx.targets import Executable


from pymake.make import InstallMode, Make

_logger = logging.getLogger('cli')

_common_opts = [
    click.option('--quiet', '-q', is_flag=True,
                 help='Dont print informations (errors only)'),
    click.option('--verbose', '-v', is_flag=True,
                 help='Pring debug informations'),
    click.argument('PATH'),
    click.argument('TARGETS', nargs=-1),
]
_base_help_ = '''
  PATH          Either build or source directory.
  [TARGETS...]  Targets to process.
'''


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func
    return _add_options


common_opts = add_options(_common_opts)


@click.group()
def commands():
    pass


def available_toolchains():
    from pymake.cxx.detect import get_toolchains
    return ['default', *[name for name in get_toolchains()['toolchains'].keys()]]


_toolchain_choice = click.Choice(available_toolchains(), case_sensitive=False)


@commands.command()
@click.option('--verbose', '-v', is_flag=True,
              help='Pring debug informations')
@click.option('--toolchain', '-t', help='The toolchain to use',
              type=_toolchain_choice)
@click.option('--setting', '-s', 'settings', help='Set or change a setting', multiple=True)
@click.option('--option', '-o', 'options', help='Set or change an option', multiple=True)
@click.argument('BUILD_PATH', type=click.Path(resolve_path=True, path_type=Path))
@click.argument('SOURCE_PATH', type=click.Path(exists=True, resolve_path=True, path_type=Path), default=Path.cwd())
def configure(verbose: bool, toolchain: str, settings: tuple[str], options: tuple[str], build_path: Path, source_path: Path):
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    config = Cache(build_path / Make._config_name)
    config.source_path = config.source_path if hasattr(
        config, 'source_path') else str(source_path)
    config.build_path = str(build_path)
    _logger.info(f'source path: {config.source_path}')
    _logger.info(f'build path: {config.build_path}')
    config.toolchain = toolchain or config.get(
        'toolchain') or click.prompt('Toolchain', type=_toolchain_choice)
    config.settings = Settings()
    asyncio.run(config.save())

    if len(settings) or len(options):
        make = Make(build_path, None, verbose, False)
        asyncio.run(make.initialize())

        if len(options):
            make.apply_options(*options)

        if len(settings):
            make.apply_settings(*settings)


@commands.command()
@click.option('--for-install', is_flag=True, help='Build for install purpose (will update rpaths [posix only])')
@common_opts
def build(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.build())
    from pymake.cxx import target_toolchain
    target_toolchain.compile_commands.update()


@commands.command()
@common_opts
@click.argument('MODE', type=click.Choice([v.name for v in InstallMode]), default=InstallMode.user.name)
def install(mode: str, **kwargs):
    make = Make(**kwargs)
    mode = InstallMode[mode]
    asyncio.run(make.install(mode))


@commands.command()
@click.option('--verbose', '-v', is_flag=True,
              help='Pring debug informations')
@click.option('--yes', '-y', is_flag=True, help='Proceed without asking')
@click.option('--root', '-r', help='Root path to search for installation manifest', type=click.Path(exists=True, file_okay=False))
@click.argument('NAME')
def uninstall(verbose: bool, yes: bool, root: str, name: str):
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    if root:
        paths = [root]
    else:
        paths = [
            '~/.local/share/pymake',
            '/usr/local/share/pymake',
            '/usr/share/pymake',
        ]
    manifest = find_file(f'{name}-manifest.txt', paths=paths)
    with open(manifest, 'r') as f:
        files = [(manifest.parent / mf.strip()).resolve()
                 for mf in f.readlines()]
    to_be_removed = '\n'.join([f" - {f}" for f in files])
    yes = yes or click.confirm(
        f'Following files will be removed:\n {to_be_removed}\nProceed ?')
    if yes:
        def rm_empty(dir: Path):
            if dir.is_empty:
                _logger.debug(f'removing empty directory: {dir}')
                os.rmdir(dir)
                rm_empty(dir.parent)

        for f in files:
            _logger.debug(f'removing: {f}')
            os.remove(f)
            rm_empty(f.parent)

        os.remove(manifest)
        rm_empty(manifest.parent)


@commands.command()
@click.option('-a', '--all', 'all', is_flag=True, help='Show all targets (not only defaulted ones)')
@click.option('-j', '--json', 'j', is_flag=True, help='Output in json format')
@click.option('-t', '--type', 'show_type', is_flag=True, help='Show target\'s type')
@common_opts
def list(all: bool, j: bool, show_type: bool, **kwargs):
    make = Make(**kwargs)
    asyncio.run(make.initialize())
    from pymake.core.include import context
    out = []
    targets = context.all_targets if all else context.default_targets
    for target in targets:
        if j:
            out.append({
                'name': target.name,
                'fullname': target.fullname,
                'buildPath': str(target.build_path),
                'output': str(target.output),
                'executable': isinstance(target, Executable),
                'type': type(target).__name__
            })
        elif show_type:
            out.append(target.fullname + ' - ' + type(target).__name__)
        else:
            out.append(target.fullname)
    if not j:
        click.echo('\n'.join(out))
    else:
        import json
        click.echo(json.dumps(out))


@commands.command()
@common_opts
def list_tests(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.initialize())
    from pymake.core.include import context
    for mf in context.all_makefiles:
        for test in mf.tests:
            click.echo(test.fullname)

@commands.command()
def list_toolchains(**kwargs):
    for name, _ in Make.toolchains()['toolchains'].items():
        click.echo(name)


@commands.command()
@common_opts
def clean(**kwargs):
    asyncio.run(Make(**kwargs).clean())


@commands.command()
@common_opts
def run(**kwargs):
    make = Make(**kwargs)
    success = asyncio.run(make.run())
    sys.exit(0 if success else 255)


@commands.command()
@common_opts
def test(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.test())


@commands.command()
@click.option('-s', '--script', help='Use a source script to resolve compilation environment')
def scan_toolchains(script: str, **kwargs):
    from pymake.cxx.detect import create_toolchains, load_env_toolchain
    if script:
        load_env_toolchain(script)
    else:
        create_toolchains()


@commands.result_callback()
def process_result(result, **kwargs):
    asyncio.run(Cache.save_all())


def main():
    import sys
    try:
        commands(auto_envvar_prefix='PYMAKE')
    except Exception as err:
        _logger.error(str(err))
        ex_type, ex, tb = sys.exc_info()
        import traceback
        _logger.debug(' '.join(traceback.format_tb(tb)))
        try:
            # wait asyncio loop to terminate
            asyncio.get_running_loop().run_until_complete()
        except Exception:
            pass
        return -1
