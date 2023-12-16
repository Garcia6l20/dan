import dataclasses
from enum import Enum
import types as typs
from click import *

import inspect
import asyncio
from dan.core.terminal import TerminalMode

import dan.core.typing as t
from dan import logging

class AsyncContext(Context):
    def invoke(__self, __callback, *args, **kwargs):
        ret = super().invoke(__callback, *args, **kwargs)
        if inspect.isawaitable(ret):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return ret  # must be awaited
            return loop.run_until_complete(ret)
        else:
            return ret


BaseCommand.context_class = AsyncContext

logger = logging.getLogger('cli')


class SettingsParamType(ParamType):
    def __init__(self, setting_cls) -> None:
        self.setting_cls = setting_cls
        self.fields = dataclasses.fields(self.setting_cls)
        super().__init__()

    def shell_complete(self, ctx, param, incomplete):
        from click.shell_completion import CompletionItem
        completions: list[str] = list()
        def gen_comps(fields, parts: list[str], prefix=''):
            part = parts[0]
            if part.startswith('"'):
                part = part[1:]
            value = None
            if '=' in part:
                part, value = part.split('=')
            elif '+=' in part or '-=' in part:
                part, value = part.split(part[:-2])
            for field in fields:
                if part.startswith(field.name):
                    type = field.type
                    if isinstance(type, typs.GenericAlias):
                        type = t.get_origin(type)
                    elif t.is_optional(type):
                        type = t.get_args(type)[0]
                    if dataclasses.is_dataclass(type):
                        subfields = dataclasses.fields(type)
                        subparts = parts[1:]
                        gen_comps(subfields, subparts, f'{field.name}.')
                    elif issubclass(type, (set, list)):
                        if part.endswith(('+', '-')):
                            completions.append(CompletionItem(f'{prefix}{field.name}{part[-1]}=', type='nospace'))
                        else:
                            for s in ('=', '+=', '-='):
                                completions.append(CompletionItem(f'{prefix}{field.name}{s}', type='nospace'))
                    elif issubclass(type, Enum):
                        for evalue in type._member_names_:
                            if value is None or evalue.startswith(value):
                                completions.append(CompletionItem(f'"{prefix}{field.name}={evalue}"'))
                    else:
                        completions.append(CompletionItem(f'{prefix}{field.name}=', type='nospace'))
                    break
                elif field.name.startswith(part):
                    type = field.type
                    if isinstance(type, typs.GenericAlias):
                        type = t.get_origin(type)
                    if dataclasses.is_dataclass(type):
                        completions.append(CompletionItem(f'{prefix}{field.name}.', type='nospace'))
                    else:
                        completions.append(CompletionItem(f'{prefix}{field.name}', type='nospace'))
        gen_comps(fields=self.fields, parts=incomplete.split('.'))
        return completions

class OptionsParamType(ParamType):
    def shell_complete(self, ctx: AsyncContext, param, incomplete):
        from click.shell_completion import CompletionItem
        from dan.make import Make
        from dan.core.asyncio import sync_wait
        build_path = ctx.params['build_path']
        make = Make(build_path, quiet=True, terminal_mode=TerminalMode.BASIC)
        sync_wait(make.initialize())
        
        comps = []
        for opt in make.all_options:
            if opt.fullname.startswith(incomplete):
                comps.append(CompletionItem(opt.fullname, type='nospace'))
        
        return comps


class TargetParamType(ParamType):
    def __init__(self, target_types=None) -> None:
        from dan.core.target import Target
        if target_types is None:
            self.target_types = (Target)
        else:
            self.target_types = tuple(target_types)
        super().__init__()

    def shell_complete(self, ctx: AsyncContext, param, incomplete):
        from click.shell_completion import CompletionItem
        from dan.make import Make
        from dan.core.asyncio import sync_wait
        build_path = ctx.params['build_path']
        make = Make(build_path, quiet=True, terminal_mode=TerminalMode.BASIC)
        sync_wait(make.initialize())

        comps = []
        for target in make.root.all_targets:
            if isinstance(target, self.target_types) and target.fullname.startswith(incomplete):
                comps.append(CompletionItem(target.fullname, type='nospace'))
        
        return comps


class ToolchainParamType(ParamType):
    def shell_complete(self, ctx: AsyncContext, param, incomplete):
        from dan.cxx.detect import get_toolchains
        from click.shell_completion import CompletionItem
        toolchains = get_toolchains(create=False)["toolchains"]
        
        comps = []
        for name in toolchains.keys():
            if name.startswith(incomplete):
                comps.append(CompletionItem(name))

        return comps
