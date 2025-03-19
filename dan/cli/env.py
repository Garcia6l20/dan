from dan.cli import click
from dan.core.terminal import set_mode as set_terminal_mode, TerminalMode
from dan.core import asyncio

from dan.cxx.base_toolchain import ToolchainSettings as CXXSettings
from dan.env import Environment, ENVIRONMENTS_PATH

from dan import logging

logger = logging.getLogger(__name__)


@click.group()
def env():
    """Manage environments."""
    set_terminal_mode(TerminalMode.BASIC)
    # logger.handlers[0].setLevel(logging.INFO)
    pass


@env.command()
@click.option("--cxx", help="CXX Toolchain to use.", type=click.ToolchainParamType())
@click.option(
    "--setting",
    "-s",
    "cxx_settings",
    help="CXX settings.",
    multiple=True,
    type=click.SettingsParamType(CXXSettings),
)
@click.option("--force", "-f", help="Force creation.", is_flag=True)
@click.argument("name")
async def new(cxx, cxx_settings, force, name):
    """Create a new environment."""

    if cxx is None:
        from dan.cxx import get_default_toolchain

        cxx = get_default_toolchain()

    logger.info("creating '%s' environment...", name)
    logger.info("cxx toolchain: %s", cxx)

    env = Environment(name, cxx, cxx_settings[0])
    env.path.mkdir(parents=True, exist_ok=force)

    await env.cache.save(force=force)


@env.command()
async def list():
    """List available environments."""
    for env in Environment.available():
        click.echo(f"{env.name}")


@env.command()
@click.argument("env", type=click.EnvironmentParamType())
async def remove(env: Environment):
    """Remove an environment."""
    logger.info("removing '%s'...", env.path)
    env.cache.ignore()
    env.path.rmdir(recursive=True)


@env.command()
@click.argument("alias")
@click.argument("env", type=click.EnvironmentParamType())
async def alias(alias, env: Environment):
    """Alias an environment."""
    alias_path = ENVIRONMENTS_PATH / alias
    if alias_path.exists():
        raise FileExistsError(f"Alias '{alias}' already exists.")
    logger.info("aliasing '%s' to '%s'...", env.path, alias_path)
    alias_path.symlink_to(env.path)


@env.command()
@click.argument("env", type=click.EnvironmentParamType())
async def show(env: Environment):
    """Show an environment."""
    click.echo(env.to_json(indent=2))
    click.echo(f"system packages: {[str(p) for p in env.system_packages]}")


_imported_libraries = set()


async def import_libraries(env: Environment, libraries, search_paths):
    from dan.pkgconfig.package import find_pkg_config, PkgConfig

    async with asyncio.TaskGroup() as tg:
        for lib in libraries:
            if lib in _imported_libraries:
                continue
            _imported_libraries.add(lib)

            logger.info("importing %s...", lib)
            pkgconf = find_pkg_config(lib, search_paths)
            if pkgconf is None:
                raise FileNotFoundError(f"Library '{lib}' not found.")
            logger.debug("pkg-config: %s", pkgconf)
            pkgconf = PkgConfig(pkgconf)
            deps = [req.name for req in pkgconf.requires]
            if deps:
                logger.debug("  dependencies: %s", deps)
                await tg.create_task(import_libraries(env, deps, search_paths))

            symlink = env.system_packages_path / pkgconf.path.name
            if symlink.exists():
                symlink.unlink()
            symlink.symlink_to(pkgconf.path)


@env.command("import")
@click.option(
    "--path",
    "-p",
    "search_paths",
    help="Path to search for libraries.",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    multiple=True,
)
@click.argument("env", type=click.EnvironmentParamType())
@click.argument("libraries", type=str, nargs=-1)
async def import_(env: Environment, libraries, search_paths):
    """Import system libraries into environment."""
    env.system_packages_path.mkdir(parents=True, exist_ok=True)
    await import_libraries(env, libraries, search_paths)


from dan.make import Make
from dan.core.version import Version, VersionSpec
from dan.core.requirements import parse_package
import os
import contextlib


_make: Make = None


async def get_make(env: Environment, quiet=True):
    global _make
    if _make is None:
        env.source_path.mkdir(parents=True, exist_ok=True)
        env.build_path.mkdir(parents=True, exist_ok=True)

        os.chdir(env.source_path)
        (env.source_path / "dan-build.py").touch()
        kwds = dict()
        if quiet:
            kwds["verbose"] = -1
        make = Make(env, **kwds)
        await make._config.save()
        await make.initialize()
        _make = make
    return _make


_repositories = None


async def get_repositories(env):
    global _repositories
    if _repositories is None:
        from dan.io.repositories import get_all_repo_instances

        await get_make(env)
        _repositories = get_all_repo_instances()
        async with asyncio.TaskGroup() as g:
            for repo in _repositories:
                g.create_task(repo.build())
    return _repositories


async def get_repository(env, name=None):
    from dan.io.repositories import get_repo_instance

    await get_make(env)
    repo = get_repo_instance(name)
    await repo.build()
    return repo


@contextlib.asynccontextmanager
async def make_context(env, quiet=False):
    make = await get_make(env, quiet=quiet)
    with make.context():
        yield make


from dan.core.settings import InstallMode, InstallSettings, BuildSettings


@env.command()
@click.option("--force", "-f", help="Force", is_flag=True)
@click.argument("env", type=click.EnvironmentParamType())
@click.argument("packages", type=str, nargs=-1)
async def install(env: Environment, packages, force):
    """Install dan packages into environment."""
    logger.info("installing %s to '%s'...", packages, env.path)
    from dan.io.package import PackageBuild, IoPackage

    async with make_context(env) as make:
        for spec in packages:
            package_spec, version_spec = VersionSpec.parse(spec)
            package, name, repository = parse_package(package_spec)
            root_makefile = make.context().root
            repository = await get_repository(env, repository)

            package_makefile, target = repository.find(name, package)
            if target is None:
                raise RuntimeError(f"cannot find {package_spec} in {repository.name}")

            logger.info("installing '%s'...", target)

            pkg = PackageBuild(
                name,
                version_spec.version if version_spec is not None else None,
                repository,
                package_makefile=package_makefile,
                packages_root=env.build_path,
                source_root=env.source_path,
                spec=version_spec,
                makefile=root_makefile,
            )

            await pkg.initialize()

            if force:
                await pkg.clean()

            if pkg.up_to_date:
                click.echo(f"Package {spec} already installed at version {pkg.version}")
            else:
                await pkg.build()
                await pkg.install(InstallSettings(env.packages_path), InstallMode.dev)
                click.echo(
                    f"Package {spec} installed successfully at version {pkg.version}"
                )
