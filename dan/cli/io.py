
import asyncio
import fnmatch
import os

from dan.cli import click
from dan.core.requirements import parse_package
from dan.make import Make

_make : Make = None
async def get_make():
    global _make
    if _make is None:
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
    return _make


_repositories = None
async def get_repositories():
    global _repositories
    if _repositories is None:
        from dan.io.repositories import get_all_repo_instances
        await get_make()
        _repositories = get_all_repo_instances()
        async with asyncio.TaskGroup() as g:
            for repo in _repositories:
                g.create_task(repo.build())
    return _repositories

async def get_repository(name = None):
    from dan.io.repositories import get_repo_instance
    await get_make()
    repo = get_repo_instance(name)
    await repo.build()
    return repo

@click.group()
def cli():
    pass

@cli.group()
def ls():
    """Inspect stuff"""
    pass


@ls.command()
async def repositories():
    """List available repositories"""
    repos = await get_repositories()
    for repo in repos:
        click.echo(repo.name)

@ls.command()
async def libraries():
    """List available libraries"""
    repos = await get_repositories()
    for repo in repos:
        for name, lib in repo.installed.items():
            click.echo(f'{name} = {lib.version}')

@ls.command()
@click.argument('LIBRARY')
async def versions(library: str):
    """Get LIBRARY's available versions"""
    package, library, repository = parse_package(library)
    repo = await get_repository(repository)
    if repo is None:
        click.logger.error(f'cannot find repository {repository}')
        return -1

    lib = repo.find(library, package)
    if lib is None:
        if repository is None:
            repository = repo.name
        if package is None:
            package = library
        click.logger.error(f'cannot find {package}:{library}@{repository}')
        return -1
    
    from dan.src.github import GitHubReleaseSources
    
    sources: GitHubReleaseSources = lib.get_dependency(GitHubReleaseSources)
    available_versions = await sources.available_versions()
    available_versions = sorted(available_versions.keys())
    for v in available_versions:
        if v == lib.version:
            click.echo(f' - {v} (default)')
        else:
            click.echo(f' - {v}')

@cli.command()
@click.argument('NAME')
async def search(name):
    """Search for NAME in repositories"""
    name = f'*{name}*'
    repos = await get_repositories()
    for repo in repos:
        installed = repo.installed
        for libname, lib in installed.items():
            if fnmatch.fnmatch(libname, name):
                click.echo(f'{libname} = {lib.version}')


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
