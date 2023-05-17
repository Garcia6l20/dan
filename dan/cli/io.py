
import asyncio
import os

from dan.cli import click
from dan.make import Make


async def get_repositories():
    from dan.io.repositories import get_all_repo_instances
    from dan.cxx.detect import get_dan_path
    source_path = get_dan_path() / 'deps'
    source_path.mkdir(exist_ok=True, parents=True)
    os.chdir(source_path)
    (source_path / 'dan-build.py').touch()
    make = Make(source_path / 'build', quiet=True)
    make.config.source_path = str(source_path)
    make.config.build_path = str(source_path / 'build')
    make.config.toolchain = 'default'
    await make._config.save()
    await make.initialize()
    return get_all_repo_instances()


@click.group()
def cli():
    pass

@cli.group()
def ls():
    pass


@ls.command()
async def repositories():
    repos = await get_repositories()
    for repo in repos:
        click.echo(repo.name)

@ls.command()
async def libraries():
    repos = await get_repositories()
    for repo in repos:
        pkgs = await repo.pkgs_makefile()
        for pkg in pkgs.children:
            for lib in pkg.all_installed:
                click.echo(f'{pkg.name}:{lib.name}@{repo.name} = {lib.version.value}')

def main():
    import sys
    try:
        cli(auto_envvar_prefix='DAN')
    except Exception as err:
        click.logger.error(str(err))
        _ex_type, _ex, tb = sys.exc_info()
        import traceback
        click.logger.debug(' '.join(traceback.format_tb(tb)))
        try:
            # wait asyncio loop to terminate
            asyncio.get_running_loop().run_until_complete()
        except Exception:
            pass
        return -1
