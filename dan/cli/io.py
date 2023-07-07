
import asyncio
import fnmatch
import os
import contextlib

from dan.cli import click
from dan.core.requirements import parse_package
from dan.core.cache import Cache
from dan.io.repositories import RepositoriesSettings, _get_settings
from dan.make import Make

def get_source_path():
    from dan.cxx.detect import get_dan_path
    source_path = get_dan_path() / 'deps'
    source_path.mkdir(exist_ok=True, parents=True)
    return source_path

_make : Make = None
async def get_make(toolchain='default', quiet=True):
    global _make
    if _make is None:
        source_path = get_source_path()
        os.chdir(source_path)
        (source_path / 'dan-build.py').touch()
        make = Make(source_path / 'build', quiet=quiet)
        make.config.source_path = str(source_path)
        make.config.build_path = str(source_path / 'build')
        make.config.toolchain = toolchain
        await make._config.save()
        await make.initialize()
        _make = make
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


@contextlib.asynccontextmanager
async def make_context(toolchain='default', quiet=True):
    make = await get_make(toolchain, quiet=quiet)
    with make.context:
        yield make


@click.group()
def cli():
    pass

@cli.command()
@click.option('--setting', '-s', 'settings', type=click.SettingsParamType(RepositoriesSettings), multiple=True)
async def configure(settings):
    io_settings = _get_settings()
    from dan.core.settings import apply_settings
    apply_settings(io_settings, *settings, logger=click.logger)
    await Cache.save_all()

@cli.group()
def ls():
    """Inspect stuff"""
    pass


@ls.command()
async def repositories():
    """List available repositories"""
    async with make_context():
        repos = await get_repositories()
        for repo in repos:
            click.echo(repo.name)

@ls.command()
async def libraries():
    """List available libraries"""
    async with make_context():
        repos = await get_repositories()
        for repo in repos:
            for name, lib in repo.installed.items():
                click.echo(f'{name} = {lib.version}')

async def get_library(library_spec):
    package, library, repository = parse_package(library_spec)
    repo = await get_repository(repository)
    if repo is None:
        raise RuntimeError(f'cannot find repository {repository}')

    lib = repo.find(library, package)
    if lib is None:
        if repository is None:
            repository = repo.name
        if package is None:
            package = library
        raise RuntimeError(f'cannot find {package}:{library}@{repository}')

    return lib

@ls.command()
@click.argument('LIBRARY')
async def versions(library: str):
    """Get LIBRARY's available versions"""
    async with make_context():
        lib = await get_library(library)
        
        from dan.src.github import GitHubReleaseSources
        
        sources: GitHubReleaseSources = lib.get_dependency(GitHubReleaseSources)
        available_versions = await sources.available_versions()
        available_versions = sorted(available_versions.keys())
        for v in available_versions:
            if v == lib.version:
                click.echo(f' - {v} (default)')
            else:
                click.echo(f' - {v}')

@ls.command()
@click.argument('LIBRARY')
async def options(library: str):
    """Get LIBRARY's available options"""
    async with make_context():
        lib = await get_library(library)
        await lib.initialize()
        for o in lib.options:
            current = ''
            if o.value != o.default:
                current = f', current: {o.value}'
            click.echo(f'{o.name}: {o.help} (type: {o.type.__name__}, default: {o.default}{current})')

@cli.command()
@click.argument('NAME')
async def search(name):
    """Search for NAME in repositories"""
    async with make_context():
        name = f'*{name}*'
        repos = await get_repositories()
        for repo in repos:
            installed = repo.installed
            for libname, lib in installed.items():
                if fnmatch.fnmatch(libname, name):
                    click.echo(f'{libname} = {lib.version}')

@cli.command()
@click.option('--toolchain', '-t', type=click.ToolchainParamType(), default='default')
@click.argument('PACKAGE_SPEC')
@click.argument('VERSION', required=False)
async def install(toolchain, package_spec, version):
    """Intall given PACKAGE_SPEC"""
    from dan.io.package import PackageBuild

    async with make_context(toolchain, quiet=False) as make:
        package, name, repository = parse_package(package_spec)
        pkg = PackageBuild(name, version, package, repository, makefile=make.root)
        await pkg.initialize()
        if pkg.up_to_date:
            click.echo(f'Package {package_spec} already installed at version {pkg.version}')
        else:
            await pkg.build()
            click.echo(f'Package {package_spec} installed successfully at version {pkg.version}')
            

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

if __name__ == '__main__':
    main()
