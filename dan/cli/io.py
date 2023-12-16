from dan import logging

import fnmatch
import os
import contextlib
from pathlib import Path

from dan.cli import click
from dan.core.requirements import parse_package
from dan.core.cache import Cache
from dan.core.runners import async_run
from dan.io.repositories import RepositoriesSettings, RepositoryConfig, _get_settings
from dan.make import Make
from dan.cxx.detect import get_dan_path
from dan.core import asyncio, aiofiles

def get_source_path():
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
        kwds = dict()
        if quiet:
            kwds['verbose'] = -1
        make = Make(source_path / 'build', **kwds)
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
@click.option('--verbose', '-v', count=True)
def cli(verbose):
    if verbose == 0:
        logging.getLogger().setLevel(logging.ERROR)
    elif verbose == 1:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.TRACE)

@cli.command()
@click.option('--setting', '-s', 'settings',
              help='Apply repository setting',
              type=click.SettingsParamType(RepositoriesSettings), multiple=True)
async def configure(settings):
    """Configure repository settings"""
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

@cli.group()
def dev():
    """Developper utils"""
    pass

@dev.command()
@click.option('--force', '-f', is_flag=True)
@click.argument('NAME')
async def create_repository(force, name):
    """Create a new package repository"""
    package_path: Path = get_dan_path() / 'repositories' / name
    if package_path.exists():
        if force or click.confirm(f'{name} repository already exists, remove it ?', default=False):
            click.logger.info('Removing existing directory %s', package_path)
            await aiofiles.rmtree(package_path)
        else:
            return -1
    click.logger.info('Create directory %s', package_path)
    package_path.mkdir()
    out, err, rc = await async_run('git init .', cwd=package_path, log=False, logger=click.logger)
    click.logger.info(out.strip())

    import jinja2
    templateEnv = jinja2.Environment(loader=jinja2.PackageLoader('dan.cli'))
    for template_name in templateEnv.list_templates(filter_func=lambda x: x.startswith('package_repository/') and not x.startswith('__')):
        dest = package_path.absolute() / template_name.removeprefix('package_repository/')
        if not dest.parent.exists():
            click.logger.debug('Creating directory %s...', dest)
            dest.parent.mkdir(parents=True)
        async with aiofiles.open(dest, 'w') as f:
            click.logger.info('Generating %s...', dest)
            await f.write(templateEnv.get_template(template_name).render(
                name = name,
            ))
        
    io_settings = _get_settings()
    if name in io_settings.repositories:
        click.logger.info('Unregistering existing %s', name)

    click.logger.info('Registering %s (with no remote)', name)
    io_settings.repositories.append(RepositoryConfig(name, url=package_path.as_uri()))
    
    await Cache.save_all()

@dev.command()
@click.option('--force', '-f', is_flag=True)
@click.option('--repo-name', prompt='Local repository name')
@click.option('--package-name', prompt='Package name')
@click.option('--package-description', prompt='Package description')
@click.option('--package-username', prompt='Github repo owner username')
@click.option('--package-projectname', prompt='Github repo project name')
@click.option('--default-version', prompt='Default github release version')
@click.option('package_requirements', '--package-requirement', multiple=True)
async def create_package(force, repo_name, package_name, **kwargs):
    repo_path = get_dan_path() / 'repositories' / repo_name
    if not repo_path.exists():
        click.logger.error('%s does not exist', repo_path)
        return -1
    packages_path: Path = get_dan_path() / 'repositories' / repo_name / 'packages'
    dest = packages_path / package_name
    if dest.exists():
        if force or click.confirm(f'{dest} package folder already exists, remove it ?', default=False):
            click.logger.info('Removing existing directory %s', dest)
            await aiofiles.rmtree(dest)
        else:
            return -1
    dest.mkdir()

    import jinja2
    templateEnv = jinja2.Environment(loader=jinja2.PackageLoader('dan.cli'))
    async with aiofiles.open(dest / 'dan-build.py', 'w') as f:
        click.logger.info('Generating %s...', dest)
        await f.write(templateEnv.get_template('package/dan-build.py').render(
            package_name = package_name,
            **kwargs
        ))
    
    packages = [d.name for d in packages_path.iterdir() if d.is_dir() and (d / 'dan-build.py').exists()]
    async with aiofiles.open(packages_path / 'dan-build.py', 'w') as f:
        await f.write(templateEnv.get_template('package_repository/packages/dan-build.py').render(
            name = repo_name,
            packages = packages,
        ))


def main():
    import sys
    try:
        sys.exit(cli(auto_envvar_prefix='DAN'))
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
