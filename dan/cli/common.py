from dan.cli import click 
from dan.core.pathlib import Path
from dan.make import Make, TerminalMode
from dan import logging

import contextlib

_minimal_options = [
    click.option('--build-path', '-B', help='Path where dan has been initialized.',
                 type=click.Path(resolve_path=True, path_type=Path), required=True, default='build', envvar='DAN_BUILD_PATH'),
]

_common_opts = [
    *_minimal_options,
    click.option('--quiet', '-q', is_flag=True,
                 help='Dont print informations (errors only).', envvar='DAN_QUIET'),
    click.option('--verbose', '-v', count=True,
                 help='Verbosity level.', envvar='DAN_VERBOSE'),
    click.option('--jobs', '-j',
                 help='Maximum jobs.', default=None, type=int, envvar='DAN_JOBS'),
    click.option('--no-status', is_flag=True,
                 help='Disable status', envvar='DAN_NOSTATUS'),
    click.option('--all', '-a', is_flag=True,
                help='Use all contexts'),
    click.option('--context', '-c', 'contexts', type=click.ContextParamType(), multiple=True,
                help='Use this context'),
]


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func
    return _add_options


common_opts = add_options(_common_opts)
minimal_options = add_options(_minimal_options)


class CommandsContext:
    def __init__(self, *args, **kwds) -> None:
        self._make_args = [*args]
        self._make_kwds = {**kwds}
        self._make = None

        logging.set_verbosity(self._make_kwds.get('verbose', None))


    def update(self, *args, **kwds):
        if len(args):
            self._make_args.extend(*args)
        self._make_kwds.update(**kwds)
    
    @contextlib.asynccontextmanager
    async def __call__(self, *args, quiet=None, no_status=False, no_init=False, code=False, context=None, **kwargs):
        if no_status:
            kwargs['terminal_mode'] = TerminalMode.BASIC
        elif code:
            kwargs['terminal_mode'] = TerminalMode.CODE
        if context:
            kwargs['contexts'] = [context]
        self.update(*args, **kwargs)
        if self._make_kwds.pop('quiet', False) or quiet:
            self._make_kwds['verbose'] = -1
        if self._make is None:
            self._make = Make(*self._make_args, **self._make_kwds)
            if not no_init:
                await self._make.initialize()
        yield self._make

    async def __aexit__(self, *exc):
        pass

pass_context = click.make_pass_decorator(CommandsContext)
