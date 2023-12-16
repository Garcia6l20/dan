import json
import os
from dan.core import asyncio

from dan.core.pm import re_match
from dan.cxx.toolchain import Toolchain

from dan.make import Make
from dan.cxx.targets import CXXObject
from dan.logging import Logging
from dan.core.utils import unique
from dan.core.pathlib import Path


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
            make_suite_info(self.make.context.root), indent=2 if pretty else None
        )

    async def _init_target(self, target):
        with target.skip_missing_dependencies:
            await target.initialize()

    async def _make_source_configuration(self, source: Path, target: CXXObject):
        # interface:
        #   - includePath: string[]
        #   - defines: string[]
        #   - intelliSenseMode?: "linux-clang-x86" | "linux-clang-x64" | "linux-clang-arm" | "linux-clang-arm64" | "linux-gcc-x86" | "linux-gcc-x64" | "linux-gcc-arm" | "linux-gcc-arm64" | "macos-clang-x86" | "macos-clang-x64" | "macos-clang-arm" | "macos-clang-arm64" | "macos-gcc-x86" | "macos-gcc-x64" | "macos-gcc-arm" | "macos-gcc-arm64" | "windows-clang-x86" | "windows-clang-x64" | "windows-clang-arm" | "windows-clang-arm64" | "windows-gcc-x86" | "windows-gcc-x64" | "windows-gcc-arm" | "windows-gcc-arm64" | "windows-msvc-x86" | "windows-msvc-x64" | "windows-msvc-arm" | "windows-msvc-arm64" | "msvc-x86" | "msvc-x64" | "msvc-arm" | "msvc-arm64" | "gcc-x86" | "gcc-x64" | "gcc-arm" | "gcc-arm64" | "clang-x86" | "clang-x64" | "clang-arm" | "clang-arm64";
        #   - standard?: "c89" | "c99" | "c11" | "c17" | "c++98" | "c++03" | "c++11" | "c++14" | "c++17" | "c++20" | "gnu89" | "gnu99" | "gnu11" | "gnu17" | "gnu++98" | "gnu++03" | "gnu++11" | "gnu++14" | "gnu++17" | "gnu++20";
        #   - forcedInclude?: string[];
        #   - compilerPath?: string;
        #   - compilerArgs?: string[];
        #   - windowsSdkVersion?: string;
        includes = await target.toolchain.get_default_include_paths()
        defines = [
            f"{k}={v}"
            for k, v in (await target.toolchain.get_default_defines()).items()
        ]
        await self._init_target(target)
        for flag in target.private_cxx_flags:
            match re_match(flag):
                case r"[/-]I:?(.+)" as m:
                    includes.append(m[1])
                case r"[/-]D:?(.+)" as m:
                    defines.append(m[1])

        config = {
            "includePath": [os.path.normcase(i) for i in unique(includes)],
            "defines": defines,
            "compilerPath": os.path.normcase(target.toolchain.cxx),
            "intelliSenseMode": get_intellisense_mode(target.toolchain),
            "compilerArgs": target.cxx_flags,
        }
        if target.cpp_std is not None:
            config["standard"] = f"c++{target.cpp_std}"
    
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
        return json.dumps(g.results())

    async def get_workspace_browse_configuration(self):
        # interface:
        #   - browsePath: string[];
        #   - compilerPath?: string;
        #   - compilerArgs?: string[];
        #   - standard?: see above
        #   - windowsSdkVersion?: string
        from dan.cxx import target_toolchain as toolchain
        from dan.cxx.targets import CXXTarget

        cpp_std = 11
        browse_path = set()
        compiler_args = set()
        cxx_targets = [
            t for t in self.make.root.all_default if isinstance(t, CXXTarget)
        ]
        async with asyncio.TaskGroup("initializing cxx targets") as g:
            for target in cxx_targets:
                g.create_task(self._init_target(target))

        for target in cxx_targets:
            browse_path.update(target.includes.private_raw)
            browse_path.update(target.includes.public_raw)
            compiler_args.update(target.cxx_flags)
            if target.cpp_std is not None and target.cpp_std > cpp_std:
                cpp_std = target.cpp_std

        from dan.pkgconfig.package import get_packages_cache

        for package in get_packages_cache().values():
            compiler_args.update(package.cxx_flags)

        result = {
            "browsePath": [os.path.normcase(p) for p in browse_path],
            "compilerPath": str(toolchain.cxx),
            "compilerArgs": list(compiler_args),
            "standard": f"c++{cpp_std}",
        }
        return json.dumps(result)
