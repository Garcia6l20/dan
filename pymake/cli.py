import click

import logging
import asyncio


from pymake.make import Make

logging.basicConfig(level=logging.INFO)

pass_make = click.make_pass_decorator(Make)


@click.group(invoke_without_command=True)
@click.option('--debug', '-d', is_flag=True, help='Pring debug informations')
@click.option('--target', '-t', help='Target to build', multiple=True)
@click.pass_context
def cli(ctx: click.Context, debug: bool, target: list[str]):
    logging.getLogger().setLevel(logging.DEBUG if debug else logging.INFO)
    ctx.obj = Make(active_targets=target)
    if ctx.invoked_subcommand is None:
        ctx.invoke(build)


@cli.command()
@pass_make
def build(make: Make):
    asyncio.run(make.build())


@cli.command()
@pass_make
def clean(make: Make):
    asyncio.run(make.clean())

@cli.command()
@pass_make
def run(make: Make):
    asyncio.run(make.run())
