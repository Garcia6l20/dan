import click

import logging
import asyncio


from pymake.make import Make

pass_make = click.make_pass_decorator(Make)

_active_targets_initialized = False
def _set_targets(ctx, param, value):
    if len(value) == 0:
        return

    global _active_targets_initialized
    if not _active_targets_initialized:
        _active_targets_initialized = True
        ctx.obj.active_targets = dict()

    found_targets = {name: target for name, target in ctx.obj.all_targets.items() if name.endswith(value)}

    if len(found_targets) == 0:
        raise RuntimeError(f"cannot math any target for name '{value}'")

    ctx.obj.active_targets.update(found_targets)

_common_opts = [
    click.argument('TARGETS', nargs=-1, callback=_set_targets)
]

def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func
    return _add_options

@click.group(invoke_without_command=True)
@click.option('--debug', '-d', is_flag=True, help='Pring debug informations')
# @click.option('--target', '-t', help='Target to build', multiple=True)
@click.pass_context
def cli(ctx: click.Context, debug: bool):
    logging.getLogger().setLevel(logging.DEBUG if debug else logging.INFO)
    ctx.obj = Make()
    if ctx.invoked_subcommand is None:
        ctx.invoke(build)


@cli.command()
@add_options(_common_opts)
@pass_make
def build(make: Make, **kwargs):
    asyncio.run(make.build())


@cli.command()
@click.option('-t', '--type', 'show_type', is_flag=True, help='Show target\'s type')
@add_options(_common_opts)
@pass_make
def list(make: Make, show_type : bool, **kwargs):
    for name, target in make.active_targets.items():
        s = name
        if show_type:
            s = s + ' - ' + type(target).__name__
        click.echo(s)

@cli.command()
@add_options(_common_opts)
@pass_make
def clean(make: Make, **kwargs):
    asyncio.run(make.clean())

@cli.command()
@add_options(_common_opts)
@pass_make
def run(make: Make, **kwargs):
    asyncio.run(make.run())
