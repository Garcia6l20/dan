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
                 help='Dont print informations (errors only).', envvar='PYMAKE_QUIET'),
    click.option('--verbose', '-v', is_flag=True,
                 help='Pring debug informations.', envvar='PYMAKE_VERBOSE'),
    click.option('--jobs', '-j',
                 help='Maximum jobs.', default=None, type=int, envvar='PYMAKE_JOBS'),
    click.option('--build-path', '-B', 'path', help='Path where pymake has been initialized.',
                 type=click.Path(resolve_path=True, path_type=Path), required=True, default='build', envvar='PYMAKE_BUILD_PATH'),
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


class CommandsContext:
    def __init__(self, *args, **kwds) -> None:
        self._make_args = [*args]
        self._make_kwds = {**kwds}
        self._make = None

    def __call__(self, *args, **kwds):
        if len(args):
            self._make_args.extend(*args)
        self._make_kwds.update(**kwds)

    @property
    def make(self):
        if self._make is None:
            self._make = Make(*self._make_args, **self._make_kwds)
        return self._make


pass_context = click.make_pass_decorator(CommandsContext)


@click.group()
@click.option('--quiet', '-q', is_flag=True,
              help='Dont print informations (errors only)')
@click.option('--verbose', '-v', is_flag=True,
              help='Pring debug informations')
@click.option('--jobs', '-j',
              help='Maximum jobs', default=None, type=int)
@click.pass_context
def cli(ctx, **kwds):
    ctx.obj = CommandsContext(**kwds)


def available_toolchains():
    from pymake.cxx.detect import get_toolchains
    return ['default', *[name for name in get_toolchains()['toolchains'].keys()]]


_toolchain_choice = click.Choice(available_toolchains(), case_sensitive=False)


@cli.command()
@click.option('--verbose', '-v', is_flag=True,
              help='Pring debug informations')
@click.option('--toolchain', '-t', help='The toolchain to use',
              type=_toolchain_choice)
@click.option('--setting', '-s', 'settings', help='Set or change a setting', multiple=True)
@click.option('--option', '-o', 'options', help='Set or change an option', multiple=True)
@click.option('--build-path', '-B', help='Path where pymake has been initialized.',
              type=click.Path(resolve_path=True, path_type=Path), required=True, default='build')
@click.option('--source-path', '-S', help='Path where source is located.',
              type=click.Path(resolve_path=True, path_type=Path), required=True, default='.')
def configure(verbose: bool, toolchain: str, settings: tuple[str], options: tuple[str], build_path: Path, source_path: Path):
    logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
    config = Cache(build_path / Make._config_name)
    config.source_path = config.source_path if hasattr(
        config, 'source_path') else str(source_path)
    config.build_path = str(build_path)
    _logger.info(f'source path: {config.source_path}')
    _logger.info(f'build path: {config.build_path}')
    config.toolchain = toolchain or config.get(
        'toolchain') or click.prompt('Toolchain', type=_toolchain_choice, default='default')
    if not hasattr(config, 'settings'):
        config.settings = Settings()
    asyncio.run(config.save())
    from pymake.core.include import context
    caches = context.get('_caches')
    caches.remove(config)
    del config

    if len(settings) or len(options):
        make = Make(build_path, None, verbose, False)
        asyncio.run(make.initialize())

        if len(options):
            make.apply_options(*options)

        if len(settings):
            make.apply_settings(*settings)

        asyncio.run(make.config.save())


@cli.command()
@click.option('--for-install', is_flag=True, help='Build for install purpose (will update rpaths [posix only])')
@common_opts
@pass_context
def build(ctx: CommandsContext, **kwds):
    ctx(**kwds)  # update kwds
    asyncio.run(ctx.make.build())
    from pymake.cxx import target_toolchain
    target_toolchain.compile_commands.update()


@cli.command()
@common_opts
@click.argument('MODE', type=click.Choice([v.name for v in InstallMode]), default=InstallMode.user.name)
@pass_context
def install(ctx: CommandsContext, mode: str, **kwargs):
    ctx(**kwargs)
    mode = InstallMode[mode]
    asyncio.run(ctx.make.install(mode))


@cli.command()
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


@cli.command()
@click.option('-a', '--all', 'all', is_flag=True, help='Show all targets (not only defaulted ones)')
@click.option('-t', '--type', 'show_type', is_flag=True, help='Show target\'s type')
@common_opts
@pass_context
def list_targets(ctx: CommandsContext, all: bool, show_type: bool, **kwargs):
    ctx(**kwargs)
    asyncio.run(ctx.make.initialize())
    from pymake.core.include import context
    out = []
    targets = context.all_targets if all else context.default_targets
    for target in targets:
        if show_type:
            out.append(target.fullname + ' - ' + type(target).__name__)
        else:
            out.append(target.fullname)
    click.echo('\n'.join(out))


@cli.command()
@common_opts
@pass_context
def list_tests(ctx: CommandsContext, **kwargs):
    ctx(**kwargs)
    asyncio.run(ctx.make.initialize())
    from pymake.core.include import context
    for test in context.root.tests:
        click.echo(test.fullname)


@cli.command()
def list_toolchains(**kwargs):
    for name, _ in Make.toolchains()['toolchains'].items():
        click.echo(name)


@cli.command()
@common_opts
def clean(**kwargs):
    asyncio.run(Make(**kwargs).clean())


@cli.command()
@common_opts
def run(**kwargs):
    make = Make(**kwargs)
    rc = asyncio.run(make.run())
    sys.exit(rc)


@cli.command()
@common_opts
def test(**kwargs):
    make = Make(**kwargs)
    rc = asyncio.run(make.test())
    sys.exit(rc)


@cli.command()
@click.option('-s', '--script', help='Use a source script to resolve compilation environment')
def scan_toolchains(script: str, **kwargs):
    from pymake.cxx.detect import create_toolchains, load_env_toolchain
    if script:
        load_env_toolchain(script)
    else:
        create_toolchains()


@cli.group()
def code():
    ''' vscode specific commands
    '''
    pass


@code.command()
@common_opts
@pass_context
def get_targets(ctx: CommandsContext, **kwargs):
    kwargs['quiet'] = True
    ctx(**kwargs)
    asyncio.run(ctx.make.initialize())
    from pymake.core.include import context
    out = []
    targets = context.all_targets
    for target in targets:
        out.append({
            'name': target.name,
            'fullname': target.fullname,
            'buildPath': str(target.build_path),
            'output': str(target.output),
            'executable': isinstance(target, Executable),
            'type': type(target).__name__
        })
    import json
    click.echo(json.dumps(out))


@cli.command()
@common_opts
@pass_context
def get_tests(ctx: CommandsContext, **kwargs):
    kwargs['quiet'] = True
    ctx(**kwargs)
    asyncio.run(ctx.make.initialize())
    from pymake.core.include import context
    out = list()
    for test in context.root.tests:
        out.append(test.fullname)
    import json
    click.echo(json.dumps(out))


@code.command()
@common_opts
@pass_context
def get_test_suites(ctx: CommandsContext, **kwargs):
    kwargs['quiet'] = True
    ctx(**kwargs)
    asyncio.run(ctx.make.initialize())
    from pymake.core.include import context, MakeFile
    from pymake.core.test import Test

    def make_test_info(test: Test):
        info = {
            'type': 'test',
            'id': test.fullname,
            'label': test.name,
            'debuggable': False,
            'target': test.executable.fullname,
            'out': str(test.out),
            'err': str(test.err),
        }
        if isinstance(test.executable, Executable):
            info['debuggable'] = True
            if test.file:
                info['file'] = str(test.file)
            else:
                info['file'] = str(
                    test.executable.source_path / test.executable.sources[0])

            if test.lineno:
                info['line'] = test.lineno

            if test.workingDir:
                info['workingDirectory'] = str(test.workingDir)
            else:
                info['workingDirectory'] = str(test.executable.build_path)

            if len(test.args) > 0:
                info['args'] = test.args

        return info

    def make_suite_info(mf: MakeFile):
        if len(mf.tests) == 0 and mf.children == 0:
            return None

        suite = {
            'type': 'suite',
            'id': mf.fullname,
            'label': mf.name,
            'children': list()
        }
        for test in mf.tests:
            suite['children'].append(make_test_info(test))

        for child in mf.children:
            child_suite = make_suite_info(child)
            if child_suite is not None:
                suite['children'].append(child_suite)

        if len(suite['children']) > 0:
            return suite

    import json
    click.echo(json.dumps(make_suite_info(context.root)))


@code.command()
def get_toolchains(**kwargs):
    import json
    click.echo(json.dumps(list(Make.toolchains()['toolchains'].keys())))


@cli.result_callback()
def process_result(result, **kwargs):
    asyncio.run(Cache.save_all())


def main():
    import sys
    try:
        cli(auto_envvar_prefix='PYMAKE')
    except Exception as err:
        _logger.error(str(err))
        _ex_type, _ex, tb = sys.exc_info()
        import traceback
        _logger.debug(' '.join(traceback.format_tb(tb)))
        try:
            # wait asyncio loop to terminate
            asyncio.get_running_loop().run_until_complete()
        except Exception:
            pass
        return -1
