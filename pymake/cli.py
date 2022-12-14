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


@commands.command()
@click.option('--toolchain', '-t', help='The toolchain to use',
              type=click.Choice(available_toolchains(), case_sensitive=False),
              prompt=True)
@click.option('--build-type', '-b', help='Build type to use',
              type=click.Choice(['debug', 'release', 'release-min-size',
                                'release-debug-infos'], case_sensitive=False),
              default='release')
@common_opts
def configure(toolchain, build_type, **kwargs):
    Make(**kwargs).configure(toolchain, build_type)


@commands.command()
@common_opts
def build(**kwargs):
    make = Make(**kwargs)
    asyncio.run(make.build())
    from pymake.cxx import target_toolchain
    target_toolchain.compile_commands.update()


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
    make = Make(**kwargs)
    asyncio.run(make.scan_toolchains(script=script))

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
