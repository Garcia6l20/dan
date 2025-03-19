from fnmatch import fnmatch
import os
import sys

from dan import logging

from dan.core.find import find_file
from dan.core.pathlib import Path
from dan.core.terminal import (
    TerminalMode,
    set_mode as set_terminal_mode,
    manager as term_manager,
)

from dan.cli import click
from dan.core.errors import InvalidConfiguration

from dan.core import diagnostics, asyncio
from dan.core.cache import Cache
from dan.core.pathlib import Path
from dan.core.settings import BuildSettings
from dan.cxx.targets import Executable


from dan.make import InstallMode, Make
from dan.cli.common import common_opts, CommandsContext, pass_context
from dan.cli.vscode import code
from dan.cli.env import env
from dan.env import Environment


logger = logging.getLogger(__name__)


@pass_context
def show_diags(ctx: CommandsContext):
    if diagnostics.enabled:
        diags = ctx._make.diagnostics
        if diags:
            click.echo(f"DIAGNOSTICS: {diags.to_json()}")


@click.group(no_args_is_help=True)
@click.version_option(package_name="dan-build")
@click.option(
    "--quiet", "-q", is_flag=True, help="Dont print informations (errors only)"
)
@click.option("--verbose", "-v", count=True, help="Verbosity level")
@click.option("--jobs", "-j", help="Maximum jobs", default=None, type=int)
@click.pass_context
def cli(ctx: click.AsyncContext, **kwds):
    ctx.obj = CommandsContext(**kwds)
    ctx.call_on_close(show_diags)


@cli.command(
    "cli",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@common_opts
@click.option("--help", is_flag=True)
@pass_context
@click.pass_context
async def user_cli_command(click_ctx, ctx, help, *args, **kwargs):
    """User commands."""
    async with ctx(no_init=False, **kwargs) as make:
        if not click_ctx.args:
            click.echo(user_cli.get_help(click_ctx))
            return 1
        args = click_ctx.args
        if help:
            args.append("--help")
        name, command, args = user_cli.resolve_command(click_ctx, click_ctx.args)
        setattr(click_ctx, "obj", make)
        cmd_ctx = command.make_context(name, args, parent=click_ctx)
        return asyncio.may_await(cmd_ctx.invoke(command))


user_cli_command.add_help_option = False


@click.group()
def user_cli():
    pass


user_cli.context_class = click.AsyncContext


@cli.command()
@click.argument(
    "context", default="default", type=click.ContextParamType(), envvar="DAN_CTX"
)
@click.option("--verbose", "-v", count=True, help="Verbosity level")
@click.option(
    "--environment",
    "-e",
    "env",
    help="The build environment to use",
    type=click.EnvironmentParamType(),
    envvar="DAN_ENV",
)
@click.option("--yes", "-y", help="Say yes to all prompts (use defaults)", is_flag=True)
@click.option(
    "--setting",
    "-s",
    "settings",
    help="Set or change a setting",
    multiple=True,
    type=click.SettingsParamType(BuildSettings),
)
@click.option(
    "--option",
    "-o",
    "options",
    help="Set or change an option",
    multiple=True,
    type=click.OptionsParamType(),
)
@click.option(
    "--build-path",
    "-B",
    help="Path where dan has been initialized.",
    type=click.Path(resolve_path=True, path_type=Path),
    required=True,
    default="build",
    envvar="DAN_BUILD_PATH",
)
@click.option(
    "--source-path",
    "-S",
    help="Path where source is located.",
    type=click.Path(resolve_path=True, path_type=Path),
    required=True,
    default=".",
    envvar="DAN_SOURCE_PATH",
)
@pass_context
async def configure(
    ctx: CommandsContext,
    context: str,
    env: Environment,
    yes: bool,
    settings: tuple[str],
    options: tuple[str],
    **kwds,
):
    """Configure project."""
    user_contexts = dict()
    async with ctx(no_init=True, no_status=True, **kwds) as make:

        if context == "auto":
            context_config = await make.project_config()
            if len(context_config) == 0:
                context = "default"
                # make.contexts = [context]
            else:
                contexts.clear()
                for ctx in context_config:
                    assert (
                        len(ctx.accepted_toolchains) > 0
                    ), f"No suitable toolchain found for {ctx.name} context"
                    contexts.append(ctx.name)
                    user_contexts[ctx.name] = {
                        "toolchains": [(t.name, s) for t, s in ctx.accepted_toolchains],
                    }

        make_ctx = make.contexts.get(context)
        if make_ctx is None or make_ctx.env is None:
            if env is None:
                if context in Environment.available():
                    env = Environment.load(context)
                else:
                    raise InvalidConfiguration("You must specify an environment to use")

            make_ctx = make.bind_context(context, env)

        await make.configure(context)

        if len(settings):
            await make.apply_settings(*settings, context=context)

        # NOTE: intializing make after applying setting
        #       to check settings are valid implicitly (cache save skipped)
        await make.initialize()

        if len(options):
            await make.apply_options(*options)


@cli.command()
@click.option(
    "--for-install",
    is_flag=True,
    help="Build for install purpose (will update rpaths [posix only])",
)
@common_opts
@click.option("--force", "-f", is_flag=True, help="Clean before building")
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def build(ctx: CommandsContext, force=False, **kwds):
    """Build targets."""
    async with ctx(**kwds) as make:
        if force:
            await make.clean()
        await make.build()


@cli.command()
@common_opts
@click.option("--force", "-f", is_flag=True, help="Force re-install")
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def install_dependencies(ctx: CommandsContext, force, **kwds):
    """Install build dependencies."""
    async with ctx(**kwds) as make:
        await make.install_dependencies(force=force)


@cli.command()
@common_opts
@click.argument(
    "MODE",
    type=click.Choice([v.name for v in InstallMode]),
    default=InstallMode.user.name,
)
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def install(ctx: CommandsContext, mode: str, **kwargs):
    """Install targets."""
    async with ctx(**kwargs) as make:
        mode = InstallMode[mode]
        await make.install(mode)


@cli.command()
@common_opts
@click.option(
    "--type", "-t", "pkg_type", type=click.Choice(["tar.gz", "zip"]), default="tar.gz"
)
@click.argument(
    "MODE",
    type=click.Choice([v.name for v in InstallMode]),
    default=InstallMode.user.name,
)
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def package(ctx: CommandsContext, pkg_type, mode: str, **kwargs):
    """Package given targets."""
    async with ctx(**kwargs) as make:
        mode = InstallMode[mode]
        await make.package(pkg_type, mode)


@cli.command()
@click.option("--verbose", "-v", count=True, help="Verbosity level")
@click.option("--yes", "-y", is_flag=True, help="Proceed without asking")
@click.option(
    "--root",
    "-r",
    help="Root path to search for installation manifest",
    type=click.Path(exists=True, file_okay=False),
)
@click.argument("NAME")
def uninstall(verbose: int, yes: bool, root: str, name: str):
    """Uninstall previous installation."""
    if verbose == 0:
        logging.getLogger().setLevel(logging.INFO)
    elif verbose == 1:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.TRACE)
    if root:
        paths = [root]
    else:
        paths = [
            "~/.local/share/dan",
            "/usr/local/share/dan",
            "/usr/share/dan",
        ]
    manifest = find_file(f"{name}-manifest.txt$", paths=paths)
    with open(manifest, "r") as f:
        files = [(manifest.parent / mf.strip()).resolve() for mf in f.readlines()]
    to_be_removed = "\n".join([f" - {f}" for f in files])
    yes = yes or click.confirm(
        f"Following files will be removed:\n {to_be_removed}\nProceed ?"
    )
    if yes:

        def rm_empty(dir: Path):
            if dir.is_empty:
                click.logger.debug(f"removing empty directory: {dir}")
                os.rmdir(dir)
                rm_empty(dir.parent)

        for f in files:
            click.logger.debug(f"removing: {f}")
            os.remove(f)
            rm_empty(f.parent)

        os.remove(manifest)
        rm_empty(manifest.parent)


@cli.group("set")
@pass_context
def _set(ctx: CommandsContext):
    """Set group."""
    ctx._make_kwds["terminal_mode"] = TerminalMode.BASIC


@_set.command()
@common_opts
@click.argument("CONTEXT", type=click.ContextParamType())
@pass_context
async def context(ctx: CommandsContext, context: str, **kwargs):
    async with ctx(no_init=True, **kwargs) as make:
        context_names = make.config.contexts.keys()
        if not context in context_names:
            avail = ", ".join(context_names)
            raise RuntimeError(f"No such context (available: {avail})")
        make.config.current_context = context
        await make.cache.save()


@_set.command()
@common_opts
@click.argument("OPTIONS", type=click.OptionsParamType(), nargs=-1)
@pass_context
async def options(ctx: CommandsContext, options, **kwargs):
    async with ctx(no_init=True, **kwargs) as make:
        await make.apply_options(*options)


@cli.group("get")
@pass_context
def _get(ctx: CommandsContext):
    """Get group."""
    ctx._make_kwds["terminal_mode"] = TerminalMode.BASIC


@_get.command()
@common_opts
@pass_context
async def context(ctx: CommandsContext, **kwargs):
    """List targets."""
    kwargs["quiet"] = True
    async with ctx(**kwargs) as make:
        click.echo(make.config.current_context)


@_get.command()
@common_opts
@pass_context
async def contexts(ctx: CommandsContext, **kwargs):
    """List targets."""
    kwargs["quiet"] = True
    async with ctx(**kwargs) as make:
        context_names = "\n".join(make.config.settings.keys())
        click.echo(context_names)


@_get.command()
@click.option(
    "-a",
    "--all",
    "all",
    is_flag=True,
    help="Show all targets (not only defaulted ones)",
)
@click.option("-t", "--type", "show_type", is_flag=True, help="Show target's type")
@common_opts
@click.argument("TARGETS", nargs=-1)
@pass_context
async def targets(ctx: CommandsContext, show_type: bool, all=False, **kwargs):
    """List targets."""
    kwargs["quiet"] = True
    async with ctx(all=all, **kwargs) as make:
        out = []
        for target in make.targets():
            name = target.display_name if all else target.name
            if show_type:
                out.append(name + " - " + type(target).__name__)
            else:
                out.append(name)
        click.echo("\n".join(out))


@_get.command()
@common_opts
@click.argument("TARGETS", nargs=-1)
@pass_context
async def tests(ctx: CommandsContext, **kwargs):
    """List tests."""
    kwargs["quiet"] = True
    async with ctx(**kwargs) as make:
        for t in make.tests:
            if len(t) > 1:
                for c in t.cases:
                    click.echo(f"{t.fullname}:{c.name}")
            else:
                click.echo(t.fullname)


@_get.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def options(ctx: CommandsContext, **kwargs):
    """List options."""
    kwargs["quiet"] = True
    async with ctx(**kwargs) as make:
        for o in make.all_options():
            click.echo(
                f"{o.fullname}: {o.help} (current: {o.value}, default: {o.default}, type: {o.type.__name__})"
            )


@_get.command()
def toolchains(**kwargs):
    """List toolchains."""
    kwargs["quiet"] = True
    for name, _ in Make.toolchains()["toolchains"].items():
        click.echo(name)


@_get.command()
@common_opts
@click.option("-n", "--not-found", help="Show not-found dependencies", is_flag=True)
@click.argument("TARGET", type=click.TargetParamType(target_types=[Executable]))
@pass_context
async def runtime_dependencies(ctx: CommandsContext, not_found, target, **kwargs):
    """Inspect stuff."""
    async with ctx(**kwargs) as make:
        for t in make.root.all_targets:
            if t.fullname == target:
                break
        from dan.cxx import ldd

        for lib, lib_path in await ldd.get_runtime_dependencies(t):
            if lib_path or not_found:
                print(" " * 7, lib, "=>", lib_path or "not found")


@cli.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def clean(ctx, **kwargs):
    """Clean generated stuff."""
    async with ctx(**kwargs) as make:
        await make.clean()


@cli.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def run(ctx, **kwargs):
    """Run executable(s)."""
    async with ctx(**kwargs) as make:
        rc = await make.run()
        sys.exit(rc)


@cli.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def test(ctx, **kwargs):
    """Run tests."""
    async with ctx(**kwargs) as make:
        rc = await make.test()
        sys.exit(rc)


@cli.command()
@click.option(
    "-s", "--script", help="Use a source script to resolve compilation environment"
)
@click.option(
    "-p",
    "--path",
    "paths",
    help="Use given path for compilers lookup",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Pring debug informations.",
    envvar="DAN_VERBOSE",
)
async def scan_toolchains(script: str, paths: list[str], verbose, **kwargs):
    """Scan system toolchains."""
    set_terminal_mode(TerminalMode.BASIC)
    match verbose:
        case 1:
            log_level = logging.DEBUG
        case 2:
            log_level = logging.TRACE
        case -1:
            log_level = logging.ERROR
        case 0:
            log_level = logging.INFO
        case _:
            logging.getLogger().warning(
                "unknown verbosity level: %s, using INFO", verbose
            )
            log_level = logging.INFO
    logging.getLogger().setLevel(log_level)
    from dan.cxx.detect import create_toolchains, load_env_toolchain

    if script:
        load_env_toolchain(script)
    else:
        create_toolchains(paths if len(paths) else None)


@cli.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def env_vars(ctx: CommandsContext, **kwargs):
    """Show environment."""
    kwargs.update({"quiet": True, "no_status": True})
    async with ctx(**kwargs) as make:
        for k, v in make.env.items():
            click.echo(f"{k}={v}")


@cli.command()
@common_opts
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def shell(ctx: CommandsContext, **kwds):
    """Open a new shell with suitable environment."""
    from dan.core.runners import sync_run

    async with ctx(**kwds) as make:
        env = dict(os.environ)
        for k, v in make.env.items():
            env[k] = v

        click.logger.info("entering dan shell...")
        click.logger.debug("env: %s", env)

        sync_run("bash", cwd=make.context().root.build_path, env=env, pipe=False)


cli.add_command(env, "env")
cli.add_command(code, "code")


@cli.result_callback()
@pass_context
async def process_result(ctx, result, **kwargs):
    from dan.core.atexit import cleanup

    await cleanup()
    await Cache.save_all()
    from dan.core.terminal import cleanup_manager

    await cleanup_manager()


def main():
    import sys

    try:
        loop = asyncio.new_event_loop()
        cli(auto_envvar_prefix="DAN")
    except Exception as err:
        click.logger.error(str(err))
        _ex_type, _ex, tb = sys.exc_info()
        import traceback

        click.logger.debug(" ".join(traceback.format_tb(tb)))
        try:
            # wait asyncio loop to terminate
            loop.run_until_complete()
        except Exception:
            pass
        asyncio.run(Cache.save_all())
        return -1
    finally:
        term = term_manager()
        term.stop()
        if term._thread:
            term._thread.get_loop().run_until_complete(term._thread)
