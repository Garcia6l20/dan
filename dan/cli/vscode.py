import json
import os
from dan.core import asyncio

from dan.core.pm import re_match
from dan.cxx.base_toolchain import Toolchain

from dan.make import Make
from dan.cxx.targets import CXXObject, Executable
from dan.logging import Logging
from dan.core.utils import unique
from dan.core.pathlib import Path
from dan.venv import VEnvironment

from dan.cli import click
from dan.cli.common import common_opts, minimal_options, pass_context, CommandsContext


def set_exception_breakpoint(
    *exceptions,
    condition: str = None,
    expression=None,
    notify_on_handled_exceptions=True,
    notify_on_unhandled_exceptions=True,
    notify_on_user_unhandled_exceptions=True,
    notify_on_first_raise_only=False,
):
    try:
        from pydevd import GetGlobalDebugger

        debugger = GetGlobalDebugger()
        for exception in exceptions:
            if isinstance(exception, type):
                exception = exception.__name__
            debugger.add_break_on_exception(
                exception,
                condition,
                expression,
                notify_on_handled_exceptions,
                notify_on_unhandled_exceptions,
                notify_on_user_unhandled_exceptions,
                notify_on_first_raise_only,
            )
    except ImportError:
        print("set_exception_breakpoint: not in vscode environment")


def get_intellisense_mode(toolchain: Toolchain):
    mode = list()
    if toolchain.system is not None:
        if toolchain.system.startswith("msys"):
            mode.append("windows")
        else:
            mode.append(toolchain.system)
    mode.append(toolchain.type)
    mode.append(toolchain.arch)
    return "-".join(mode)


class Code(Logging):
    fullname = "code"

    def __init__(self, make: Make) -> None:
        self.make = make

    def get_test_suites(self, pretty):
        from dan.core.include import MakeFile
        from dan.core.test import Test, Case
        from dan.cxx import Executable

        def make_inner_test_info(test: Test, case: Case):
            basename = test.basename(case)
            out, err = test.outs(case)
            ident = (
                f"{test.fullname}:{case.name}"
                if case.name is not None
                else test.fullname
            )
            info = {
                "type": "test",
                "id": ident,
                "label": basename,
                "debuggable": False,
                "target": test.executable.fullname,
                "out": str(out),
                "err": str(err),
            }
            if isinstance(test.executable, Executable):
                info["debuggable"] = True
                if case.file:
                    info["file"] = str(case.file)
                elif test.file:
                    info["file"] = str(test.file)
                else:
                    info["file"] = str(
                        test.executable.source_path / test.executable.sources[0]
                    )

                if case.lineno:
                    info["line"] = case.lineno
                elif test.lineno:
                    info["line"] = test.lineno

                if test.workingDir:
                    info["workingDirectory"] = str(test.workingDir)
                else:
                    info["workingDirectory"] = str(test.executable.build_path)

                if len(case.args) > 0:
                    info["args"] = [str(a) for a in case.args]

            return info

        def make_test_info(test: Test):
            if len(test) == 0:
                raise RuntimeError(f"Test: {test.name} has not test")
            if len(test) == 1:
                return make_inner_test_info(test, test.cases[0])
            else:
                return {
                    "type": "suite",
                    "id": test.fullname,
                    "label": test.name,
                    "children": [
                        make_inner_test_info(test, case) for case in test.cases
                    ],
                }

        def make_suite_info(mf: MakeFile):
            if len(mf.tests) == 0 and mf.children == 0:
                return None
            children = list()
            for test in mf.tests:
                children.append(make_test_info(test))

            for child in mf.children:
                child_suite = make_suite_info(child)
                if child_suite is not None:
                    children.append(child_suite)

            if len(children) > 0:
                return {
                    "type": "suite",
                    "id": mf.fullname,
                    "label": mf.name,
                    "children": children,
                }

        return json.dumps(
            make_suite_info(self.make.context().root), indent=2 if pretty else None
        )

    async def _init_target(self, target):
        with target.skip_missing_dependencies:
            await target.initialize()

    async def _make_source_configuration(self, source: Path, target: CXXObject):
        await self._init_target(target)

        cc, *args = target.toolchain.get_base_compile_args(
            lang=target.lang,
            cpp_std=target.cpp_std,
            build_type=target.makefile.context.venv.cxx_settings.build_type,
        )

        config = {
            "includePath": [os.path.normcase(i) for i in target.includes.all_raw],
            "defines": list(target.compile_definitions.all_raw),
            "compilerPath": os.path.normcase(cc),
            "compilerArgs": [],
            "compilerFragments": args,
        }

        return {
            "uri": str(source),
            "configuration": config,
        }

    async def get_sources_configuration(self, sources):
        targets_map = await self.make.targets_of(sources)

        async with asyncio.TaskGroup() as g:
            for source, target in targets_map.items():
                if target:
                    g.create_task(self._make_source_configuration(source, target))

        return json.dumps(list(g.results()))

    async def get_workspace_browse_configuration(self):
        from dan.cxx.targets import CXXTarget

        context = self.make.context()
        root = context.root
        toolchain = context.get("cxx_toolchain")

        cpp_std = 17
        browse_path = set()
        cxx_targets = [t for t in root.all_default if isinstance(t, CXXTarget)]
        async with asyncio.TaskGroup("initializing cxx targets") as g:
            for target in cxx_targets:
                g.create_task(self._init_target(target))

        for target in cxx_targets:
            browse_path.add(target.makefile.source_path)
            if target.cpp_std is not None and target.cpp_std > cpp_std:
                cpp_std = target.cpp_std

        cc, *args = target.toolchain.get_base_compile_args(
            lang=target.lang,
            cpp_std=cpp_std,
            build_type=target.makefile.context.venv.cxx_settings.build_type,
        )

        result = {
            "browsePath": [os.path.normcase(p) for p in browse_path],
            "compilerPath": str(toolchain.cxx),
            "compilerArgs": [],
            "compilerFragments": args,
        }
        return json.dumps(result)


@click.group()
def code():
    """VS-Code specific commands."""


from dan.core.bench import benchmark, report_all


@code.command()
@click.option("--benchmark", "report_benchmark", is_flag=True)
@common_opts
@click.argument("CONTEXT", nargs=-1)
@pass_context
async def get_targets(ctx: CommandsContext, report_benchmark, **kwargs):
    """Get targets."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    with benchmark("get-targets") as bench:
        make_init = bench.begin("make-init")
        async with ctx(**kwargs) as make:
            make_init.end()
            out = []
            targets = make.context().root.all_targets
            with bench("load-dependencies"):
                async with asyncio.TaskGroup() as g:
                    for target in targets:
                        g.create_task(target.load_dependencies())
                with bench("gen-output"):
                    for target in targets:
                        with bench(f"gen-output-{target.name}"):
                            out.append(
                                {
                                    "name": target.name,
                                    "fullname": target.fullname,
                                    "buildPath": str(target.build_path),
                                    "srcPath": str(target.source_path),
                                    "output": str(target.output),
                                    "executable": isinstance(target, Executable),
                                    "type": type(target).__name__,
                                    "env": (
                                        target.env
                                        if isinstance(target, Executable)
                                        else None
                                    ),
                                }
                            )
                with bench("json-dump"):
                    click.echo(json.dumps(out))
    if report_benchmark:
        report_all()


@code.command()
@common_opts
@click.argument("TARGETS", nargs=-1)
@pass_context
async def get_tests(ctx: CommandsContext, **kwargs):
    """Get tests."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    async with ctx(**kwargs) as make:
        out = list()
        for t in make.context().root.all_tests:
            out.append(t.fullname)
            if len(t) > 1:
                for c in t.cases:
                    out.append(f"{t.fullname}:{c.name}")
        click.echo(json.dumps(out))


@code.command()
@common_opts
@click.option("--pretty", is_flag=True)
@click.argument("TARGETS", nargs=-1)
@pass_context
async def get_test_suites(ctx: CommandsContext, pretty, **kwargs):
    """Get test suites."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    async with ctx(**kwargs) as make:
        code = Code(make)
        click.echo(code.get_test_suites(pretty))


@code.command()
def get_toolchains(**kwargs):
    """Get toolchains."""
    click.echo(json.dumps(list(Make.toolchains()["toolchains"].keys())))


@code.command()
@common_opts
@pass_context
async def get_buildfiles(ctx: CommandsContext, **kwargs):
    """Get buildfiles."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    async with ctx(**kwargs) as make:
        builfiles = [f.__file__ for f in make.makefiles()]
        click.echo(json.dumps(builfiles))


@code.command()
@common_opts
@pass_context
async def get_environments(ctx: CommandsContext, **kwargs):
    """Get environments."""
    click.echo(json.dumps([e.name for e in VEnvironment.available()]))


@code.command()
@common_opts
@pass_context
@click.argument("NAME")
async def get_environment(ctx: CommandsContext, name, **kwargs):
    """Get environments."""
    click.echo(VEnvironment.load(name).to_json())


@code.command()
@click.option(
    "--for-install",
    is_flag=True,
    help="Build for install purpose (will update rpaths [posix only])",
)
@click.option(
    "--context",
    "-c",
    "contexts",
    type=click.ContextParamType(),
    multiple=True,
    help="Use this context",
)
@common_opts
@click.option("--force", "-f", is_flag=True, help="Clean before building")
@click.argument("TARGETS", nargs=-1, type=click.TargetParamType())
@pass_context
async def build(ctx: CommandsContext, force=False, **kwargs):
    """Build targets (vscode version)."""
    async with ctx(**kwargs, diags=True, code=True) as make:
        if force:
            await make.clean()
        await make.build()


@code.command()
@minimal_options
@click.argument(
    "SOURCES", nargs=-1, type=click.Path(exists=True, dir_okay=False, resolve_path=True)
)
@pass_context
async def get_source_configuration(ctx: CommandsContext, sources, **kwargs):
    """Get source configuration."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    async with ctx(**kwargs) as make:
        code = Code(make)
        click.echo(await code.get_sources_configuration(sources))


@code.command()
@minimal_options
@pass_context
async def get_workspace_browse_configuration(ctx: CommandsContext, **kwargs):
    """Get workspace browse configuration."""
    kwargs.update({"quiet": True, "diags": True, "no_status": True})
    async with ctx(**kwargs) as make:
        code = Code(make)
        click.echo(await code.get_workspace_browse_configuration())


@code.command()
@common_opts
@click.argument("CONTEXT")
@pass_context
async def get_options(ctx: CommandsContext, context, **kwargs):
    """Get options."""
    kwargs.update(
        {"quiet": True, "diags": True, "no_status": True, "contexts": [context]}
    )
    async with ctx(**kwargs) as make:
        opts = list()
        for o in make.all_options():
            opts.append(
                {
                    "name": o.name,
                    "fullname": o.fullname,
                    "help": o.help,
                    "type": o.type.__name__,
                    "value": o.value,
                    "default": o.default,
                }
            )
        click.echo(json.dumps(opts))
