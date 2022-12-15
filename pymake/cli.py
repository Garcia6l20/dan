from pymake.core.pathlib import Path
import click

import logging
import asyncio
from pymake.core.cache import Cache


from pymake.make import Make

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
    return [name for name in get_toolchains()['toolchains'].keys()]


_toolchain_choice = click.Choice(available_toolchains(), case_sensitive=False)


@commands.command()
@click.option('--verbose', '-v', is_flag=True,
              help='Pring debug informations')
@click.option('--toolchain', '-t', help='The toolchain to use',
              type=_toolchain_choice)
@click.option('--build-type', '-b', help='Build type to use',
              type=click.Choice(['debug', 'release', 'release-min-size',
                                'release-debug-infos'], case_sensitive=False),
              default='release')
@click.option('--setting', '-s', 'settings', help='Set or change a setting', multiple=True)
@click.option('--option', '-o', 'options', help='Set or change an option', multiple=True)
@click.argument('BUILD_PATH', type=click.Path(resolve_path=True, path_type=Path))
@click.argument('SOURCE_PATH', type=click.Path(exists=True, resolve_path=True, path_type=Path), default=Path.cwd())
def configure(verbose: bool, toolchain: str, build_type: str, settings: tuple[str], options: tuple[str], build_path: Path, source_path: Path):
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    config = Cache(build_path / Make._config_name)
    config.source_path = config.source_path if hasattr(config, 'source_path') else str(source_path)
    config.build_path = str(build_path)
    _logger.info(f'source path: {config.source_path}')
    _logger.info(f'build path: {config.build_path}')
    config.toolchain = toolchain or config.toolchain if hasattr(config, 'toolchain') else click.prompt(
        'Toolchain', type=_toolchain_choice)
    config.build_type = build_type or config.build_type

    if len(settings) or len(options):
        asyncio.run(config.save())

        make = Make(build_path, None, verbose, False)
        asyncio.run(make.initialize())

        if len(options):
            all_opts = make.all_options()
            for option in options:
                name, value = option.split('=')
                found = False
                for opt in all_opts:
                    if opt.fullname == name:
                        found = True
                        opt.value = value
                        break
                assert found, f'No such option \'{name}\', available options: {[o.fullname for o in all_opts]}'

        if len(settings):
            raise NotImplementedError('Settings not implemented yet')


    asyncio.run(config.save())


@commands.command()
@common_opts
def build(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.build())
    from pymake.cxx import target_toolchain
    target_toolchain.compile_commands.update()

# @commands.command()
# def install(**kwargs):
#     make = Make(**kwargs)
#     asyncio.run(make.install())


@commands.command()
@click.option('-a', '--all', 'all', is_flag=True, help='Show all targets (not only defaulted ones)')
@click.option('-t', '--type', 'show_type', is_flag=True, help='Show target\'s type')
@common_opts
def list(all: bool, show_type: bool, **kwargs):
    make = Make(**kwargs)
    asyncio.run(make.initialize())
    from pymake.core.target import Target

    targets = Target.all if all else Target.default
    for target in targets:
        s = target.fullname
        if show_type:
            s = s + ' - ' + type(target).__name__
        click.echo(s)


@commands.command()
def list_toolchains(**kwargs):
    make = Make(**kwargs)
    for name, _ in make.toolchains['toolchains'].items():
        click.echo(name)


@commands.command()
@common_opts
def clean(**kwargs):
    asyncio.run(Make(**kwargs).clean())


@commands.command()
@common_opts
def run(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.run())


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
