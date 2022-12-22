
import functools
import logging
import os
from pymake.core.pathlib import Path
import sys
import tqdm

from pymake.core.cache import Cache
from pymake.core.include import include_makefile
from pymake.core import aiofiles, asyncio
from pymake.core.settings import InstallMode, Settings, safe_load
from pymake.core.utils import unique
from pymake.cxx import init_toolchains
from pymake.logging import Logging
from pymake.core.target import Option, Target
from pymake.cxx.targets import Executable
from collections.abc import Iterable


def make_target_name(name: str):
    return name.replace('_', '-')


def flatten(list_of_lists):
    if len(list_of_lists) == 0:
        return list_of_lists
    if isinstance(list_of_lists[0], Iterable):
        return flatten(list_of_lists[0]) + flatten(list_of_lists[1:])
    return list_of_lists[:1] + flatten(list_of_lists[1:])


class Make(Logging):
    _config_name = 'pymake.config.yaml'
    _cache_name = 'pymake.cache.yaml'

    def __init__(self, path: str, targets: list[str] = None, verbose: bool = False, quiet: bool = False, for_install: bool = False):

        from pymake.core.include import context_reset
        context_reset()

        if quiet:
            assert not verbose, "'quiet' cannot be combined with 'verbose'"
            log_level = logging.ERROR
        elif verbose:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO
        logging.getLogger().setLevel(log_level)

        super().__init__('make')

        self.config = None
        self.cache = None
        self.for_install = for_install
        path = Path(path)
        if not path.exists() or not (path / 'makefile.py').exists():
            self.source_path = Path.cwd().absolute()
            self.build_path = path.absolute().resolve()
        else:
            self.source_path = path.absolute().resolve()
            self.build_path = Path.cwd().absolute()

        self.config_path = self.build_path / self._config_name
        self.cache_path = self.build_path / self._cache_name

        self.required_targets = targets
        self.build_path.mkdir(exist_ok=True, parents=True)
        sys.pycache_prefix = str(self.build_path / '__pycache__')
        self.config = Cache(self.config_path)
        self.cache = Cache(self.cache_path)

        self.settings: Settings = self.config.get('settings', Settings())

        self.source_path = Path(self.config.get(
            'source_path', self.source_path))

        self.debug(f'source path: {self.source_path}')
        self.debug(f'build path: {self.build_path}')

        assert (self.source_path /
                'makefile.py').exists(), f'no makefile in {self.source_path}'
        assert (self.source_path !=
                self.build_path), f'in-source build are not allowed'

    def configure(self, toolchain):
        self.config.source_path = str(self.source_path)
        self.config.build_path = str(self.build_path)
        self.config.toolchain = toolchain

    @asyncio.once_method
    async def initialize(self):
        assert self.source_path and self.config_path.exists(), 'configure first'

        toolchain = self.config.toolchain
        build_type = self.settings.build_type
        init_toolchains(toolchain)

        self.info(f'using \'{toolchain}\' toolchain in \'{build_type.name}\' mode')
        include_makefile(self.source_path, self.build_path)

        from pymake.core.include import context
        from pymake.cxx import target_toolchain
        target_toolchain.build_type = build_type
        if self.for_install:
            library_dest = Path(self.settings.install.destination) / \
                self.settings.install.libraries_prefix
            target_toolchain.set_rpath(str(library_dest.absolute()))

        self.active_targets: dict[str, Target] = dict()

        if self.required_targets and len(self.required_targets) > 0:
            for target in context.all_targets:
                if target.name in self.required_targets or target.fullname in self.required_targets:
                    self.active_targets[target.fullname] = target
        else:
            for target in context.default_targets:
                self.active_targets[target.fullname] = target

        self.debug(f'targets: {[name for name in self.active_targets.keys()]}')

    @staticmethod
    def all_options() -> list[Option]:
        from pymake.core.include import context
        opts = []
        for target in context.all_targets:
            for o in target.options:
                opts.append(o)
        for makefile in context.all_makefiles:
            for o in makefile.options:
                opts.append(o)
        return opts

    def apply_options(self, *options):
        all_opts = self.all_options()
        for option in options:
            name, value = option.split('=')
            found = False
            for opt in all_opts:
                if opt.fullname == name:
                    found = True
                    opt.value = value
                    break
            assert found, f'No such option \'{name}\', available options: {[o.fullname for o in all_opts]}'

    def apply_settings(self, *settings):
        for setting in settings:
            name, value = setting.split('=')
            parts = name.split('.')
            setting = self.settings
            for part in parts[:-1]:
                if not hasattr(setting, part):
                    raise RuntimeError(f'no such setting: {name}')
                setting = getattr(setting, part)
            if not hasattr(setting, parts[-1]):
                raise RuntimeError(f'no such setting: {name}')
            value = safe_load(name, value, type(getattr(setting, parts[-1])))
            setattr(setting, parts[-1], value)

    @staticmethod
    def get(*names) -> list['Target']:
        from pymake.core.include import context
        targets = list()
        for name in names:
            found = False
            for target in context.all_targets:
                if name in [target.fullname, target.name]:
                    found = True
                    targets.append(target)
                    break
            if not found:
                raise RuntimeError(f'target not found: {name}')
        return targets

    @staticmethod
    def toolchains():
        from pymake.cxx.detect import get_toolchains
        return get_toolchains()

    class progress:
        
        def __init__(self, desc, targets, task_builder) -> None:
            self.desc = desc
            self.targets = targets
            self.builder = task_builder
            import shutil
            term_cols = shutil.get_terminal_size().columns
            self.max_desc_width = int(term_cols * 0.25)
            self.pbar = tqdm.tqdm(total=len(targets), desc='building')
            self.pbar.unit = ' targets'

        def __enter__(self):
            def update(n=1):
                desc = self.desc + ' ' + \
                    ', '.join([t.name for t in self.targets])                
                if len(desc) > self.max_desc_width:
                    desc = desc[:self.max_desc_width] + ' ...'
                self.pbar.set_description_str(desc)
                self.pbar.update(n)
            update(0)

            def on_done(t: Target, *args, **kwargs):
                self.targets.remove(t)
                update()

            tasks = list()

            for t in self.targets:
                tsk = asyncio.create_task(self.builder(t))
                tsk.add_done_callback(functools.partial(on_done, t))
                tasks.append(tsk)

            return tasks

        def __exit__(self, *args):
            self.pbar.set_description_str(self.desc + ' done')
            self.pbar.refresh()
            return

    async def build(self):
        await self.initialize()
        targets = set(self.active_targets.values())

        with self.progress('building', targets, lambda t: t.build()) as tasks:
            await asyncio.gather(*tasks)

    async def install(self, mode: InstallMode = InstallMode.user):

        from pymake.core.include import context

        self.for_install = True
        destination = Path(self.settings.install.destination)
        if not destination.is_absolute():
            self.settings.install.destination = str(Path.cwd() / destination)

        await self.initialize()
        self.active_targets = dict()
        for target in context.installed_targets:
            self.active_targets[target.fullname] = target

        await self.build()

        targets = list(self.active_targets.values())
        with self.progress('installing', targets, lambda t: t.install(self.settings.install, mode)) as tasks:
            installed_files = await asyncio.gather(*tasks)
            installed_files = unique(flatten(installed_files))
            manifest_path = self.settings.install.data_destination / \
                'pymake' / f'{context.root.name}-manifest.txt'
            manifest_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(manifest_path, 'w') as f:
                await f.writelines([os.path.relpath(p, manifest_path.parent) + '\n' for p in installed_files])

    @property
    def executable_targets(self) -> list[Executable]:
        return [exe for exe in self.active_targets.values() if isinstance(exe, Executable)]

    async def scan_toolchains(self, script: Path = None):
        from pymake.cxx.detect import create_toolchains, load_env_toolchain
        if script:
            load_env_toolchain(script)
        else:
            create_toolchains()

    async def run(self):
        await self.initialize()
        await asyncio.gather(*[t.execute(pipe=False) for t in self.executable_targets])

    async def test(self):
        await self.initialize()
        tests = list()
        from pymake.core.include import context
        for makefile in context.all_makefiles:
            for test in makefile.tests:
                tests.append(test)
        with self.progress('testing', tests, lambda t: t.__call__()) as tasks:
            results = await asyncio.gather(*tasks)
            if all(results):
                self.info('Success !')
                return False
            else:
                self.error('Failed !')
                return True

    async def clean(self, target: str = None):
        await self.initialize()
        from pymake.cxx import toolchain
        toolchain.scan = False
        from pymake.core.target import Target
        Target.clean_request = True
        await asyncio.gather(*[t.clean() for t in self.active_targets.values()])
        from pymake.cxx import target_toolchain

        target_toolchain.compile_commands.clear()
