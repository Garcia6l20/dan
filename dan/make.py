
from dataclasses import dataclass, field
from enum import Enum
import functools
import itertools
import os
import fnmatch
import re

from dataclasses_json import dataclass_json
import sys
import tqdm
from collections.abc import Iterable

from dan import logging

import dan.core.typing as t
from dan.core import diagnostics as diag
from dan.core.cache import Cache
from dan.core.makefile import MakeFile
from dan.core.pathlib import Path
from dan.core.include import MakeFileError, include_makefile, Context
from dan.core import aiofiles, asyncio
from dan.core.requirements import load_requirements
from dan.core.settings import InstallMode, InstallSettings, Settings
from dan.core.test import Test
from dan.core.utils import unique
from dan.cxx import init_toolchains
from dan.core.target import Option, Target
from dan.cxx.targets import Executable
from dan.core.runners import max_jobs


def flatten(list_of_lists):
    if len(list_of_lists) == 0:
        return list_of_lists
    if isinstance(list_of_lists[0], Iterable):
        return flatten(list_of_lists[0]) + flatten(list_of_lists[1:])
    return list_of_lists[:1] + flatten(list_of_lists[1:])

@dataclass_json
@dataclass
class Config:
    source_path: Path = None
    build_path: Path = None
    toolchain: str = None
    settings: Settings = field(default_factory=lambda: Settings())

class ConfigCache(Cache[Config]):
    indent = 4

def _get_code_position(code, instruction_index):
    if instruction_index < 0 \
        or not hasattr(code, 'co_positions'): # Python <= 3.10 does not have co_position
        return (None, 0, 0, 0)
    positions_gen = code.co_positions()
    return next(itertools.islice(positions_gen, instruction_index // 2, None))

def _tb_entries(tb):
    entries = list()
    while tb is not None:
        entries.append(tb)
        tb = tb.tb_next
    return entries


def _walk_tb(tb, reverse=True):
    if isinstance(tb, Exception):
        tb = tb.__traceback__

    entries = _tb_entries(tb)
    
    if reverse:
        entries = reversed(entries)
    
    for tb in entries:
        positions = _get_code_position(tb.tb_frame.f_code, tb.tb_lasti)
        # Yield tb_lineno when co_positions does not have a line number to
        # maintain behavior with walk_tb.
        if positions[0] is None:
            yield tb.tb_frame.f_code.co_filename, (tb.tb_lineno, ) + positions[1:]
        else:
            yield tb.tb_frame.f_code.co_filename, positions


def gen_python_diags(err: Exception):
    diagnostics = diag.DiagnosticCollection()
    if not diag.enabled:
        return diagnostics
    match err:
        case MakeFileError():
            cause = err.__cause__
            related = None
            if isinstance(cause, MakeFileError):
                related = list()
                cause_diags = gen_python_diags(cause)
                for filename, diagns in cause_diags.items():
                    for d in diagns:
                        related.append(diag.RelatedInformation(diag.Location(diag.Uri(filename), d.range), d.message))
                diagnostics.update(cause_diags)
                err_filename = str(err.path)
                for filename, (lineno, end_lineno, colno, end_colno) in _walk_tb(cause):
                    if filename == err_filename:
                        break
            else:
                for filename, (lineno, end_lineno, colno, end_colno) in _walk_tb(cause):
                    break
            diagnostics[filename] = diag.Diagnostic(
                message=str(cause),
                range=diag.Range(start=diag.Position(lineno - 1, colno), end=diag.Position(end_lineno - 1, end_colno)),
                code=cause.__class__.__name__,
                source='dan.make',
                related_information=related
            )
        case _:
            for filename, (lineno, end_lineno, colno, end_colno) in _walk_tb(err):
                break
            diagnostics[filename] = diag.Diagnostic(
                message=str(err),
                range=diag.Range(start=diag.Position(lineno - 1, colno), end=diag.Position(end_lineno - 1, end_colno)),
                code=err.__class__.__name__,
                source='dan.make'
            )

    return diagnostics

class Make(logging.Logging):
    _config_name = 'dan.config.json'
    _cache_name = 'dan.cache'

    def __init__(self, build_path: str, targets: list[str] = None, verbose: int = 0, for_install: bool = False, jobs: int = None, no_progress=False, diags=False):

        jobs = jobs or os.cpu_count()
        max_jobs(jobs)

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
                logging.getLogger().warning('unknown verbosity level: %s, using INFO', verbose)
                log_level = logging.INFO

        logging.getLogger().setLevel(log_level)

        super().__init__('make')

        if diags:
            diag.enabled = True

        self.no_progress = no_progress
        self.for_install = for_install
        
        self.build_path = Path(build_path)
        self.config_path = build_path / self._config_name
        self.cache_path = build_path / self._cache_name

        self.required_targets = targets
        sys.pycache_prefix = str(build_path / '__pycache__')
        self._config = ConfigCache.instance(self.config_path)
        self.cache = Cache.instance(self.cache_path, binary=True)
        
        self.debug(f'jobs: {jobs}')

        self._diagnostics = diag.DiagnosticCollection()

        self.context = Context()
        
    @property
    def config(self) -> Config:
        return self._config.data
    
    @property
    def settings(self) -> Settings:
        return self._config.data.settings
    
    @property
    def source_path(self):
        return Path(self.config.source_path)
        
    @property
    def toolchain(self):
        return self.context.get('cxx_target_toolchain')
    
    @property
    def root(self) -> MakeFile:
        return self.context.root
    
    @property
    def env(self) -> dict[str, str]:
        from dan.cxx.detect import get_dan_path
        env = self.toolchain.env
        epath = env.get('PATH', os.environ['PATH']).split(os.pathsep)
        epath.insert(0, str(get_dan_path() / 'os-utils' / 'bin'))
        for t in self.executable_targets:
            parts = t.env.get('PATH', os.environ['PATH']).split(os.pathsep)
            for p in parts:
                if not p in epath:
                    epath.append(p)
        env['PATH'] = os.pathsep.join(epath)
        return env

    async def configure(self, source_path: str, toolchain: str = None):
        self.config.source_path = str(source_path)
        self.config.build_path = str(self.build_path)
        self.info(f'source path: {self.config.source_path}')
        self.info(f'build path: {self.config.build_path}')
        if toolchain:
            self.config.toolchain = toolchain
        if not self.config.toolchain:
            self.warning('no toolchain configured')
        await self._config.save()

    @asyncio.cached
    async def initialize(self):
        assert self.config_path.exists(), 'configure first'

        self.debug(f'source path: {self.source_path}')
        self.debug(f'build path: {self.build_path}')

        toolchain = self.config.toolchain
        build_type = self.settings.build_type

        self.info(
            f'using \'{toolchain}\' toolchain in \'{build_type.name}\' mode')

        with self.context:
            init_toolchains(toolchain, self.settings)
            try:
                include_makefile(self.source_path, self.build_path)
            except MakeFileError as err:
                self._diagnostics.update(gen_python_diags(err))
                raise

        target_toolchain = self.context.get('cxx_target_toolchain')
        target_toolchain.build_type = build_type
        if self.for_install:
            library_dest = Path(self.settings.install.destination) / \
                self.settings.install.libraries_prefix
            target_toolchain.rpath = str(library_dest.absolute())

        self.debug(f'targets: {[t.name for t in self.targets]}')

    def __matches(self, target: Target | Test):
        for required in self.required_targets:
            if fnmatch.fnmatch(target.fullname, f'*{required}*'):
                return True
        return False

    @functools.cached_property
    def targets(self) -> list[Target]:
        items = list()
        if self.required_targets and len(self.required_targets) > 0:
            for target in self.root.all_targets:
                if self.__matches(target):
                    items.append(target)
        else:
            items = self.root.all_default
        return items

    @functools.cached_property
    def tests(self) -> list[Test]:
        items = list()
        if self.required_targets and len(self.required_targets) > 0:
            for required in self.required_targets:
                pos = required.find(':')
                if pos > 0:
                    test_name = required[:pos]
                    test_case = required[pos+1:]
                else:
                    test_name = required
                    test_case = None

                for test in self.root.all_tests:
                    
                    if fnmatch.fnmatch(test.fullname, f'*{test_name}*'):
                        if len(test) > 1 and test_case is not None:
                            cases = list()
                            for case in test.cases:
                                if fnmatch.fnmatch(case.name, test_case):
                                    cases.append(case)
                            if len(cases) == 0:
                                self.warning('couldn\'t find any test case in %s matching \'%s\'', test.name, test_case)
                            test.cases = cases
                        
                        items.append(test)
        else:
            for test in self.root.all_tests:
                items.append(test)
        return items

    @property
    def all_options(self) -> list[Option]:
        opts = []
        for target in self.targets:
            for o in target.options:
                opts.append(o)
        for makefile in self.context.all_makefiles:
            for o in makefile.options:
                opts.append(o)
        return opts
    
    @property
    def diagnostics(self):
        result: diag.DiagnosticCollection = diag.DiagnosticCollection()
        if self.root:
            for target in self.root.all_targets:
                result.update(target.diagnostics)
        result.update(self._diagnostics)
        return result


    async def target_of(self, source: Path):
        from dan.cxx.targets import CXXObjectsTarget

        source = Path(source)
        if source.suffix[1].lower() == 'h':
            def check(t: CXXObjectsTarget):
                for p in [*t.includes.private_raw, *t.includes.public_raw]:
                    p: Path = p
                    if p not in source.parents:
                        continue
                    return True
                return False
        else:
            def check(t: CXXObjectsTarget):
                t._init_sources()
                if source.name in [Path(s).name for s in target.sources]:
                    return True
                return False
        for target in [target for target in self.root.all_targets if isinstance(target, CXXObjectsTarget)]:            
            if target.source_path not in source.parents:
                continue
            if check(target):
                return target

    async def apply_options(self, *options):
        await self.initialize()
        from dan.core.settings import _apply_inputs
        all_opts = self.all_options
        def get_option(name):
            for opt in all_opts:
                if opt.fullname == name:
                    return opt.cache, opt.value, opt.type
        _apply_inputs(options, get_option, logger=self, input_type_name='option')

    async def apply_settings(self, *settings):
        from dan.core.settings import apply_settings
        apply_settings(self.settings, *settings, logger=self)


    @staticmethod
    def toolchains():
        from dan.cxx.detect import get_toolchains
        return get_toolchains()

    class progress:

        def __init__(self, desc, targets, task_builder, disable) -> None:
            self.desc = desc
            self.targets = list(targets) # NOTE: need to take a copy of the list
            self.builder = task_builder
            import shutil
            term_cols = shutil.get_terminal_size().columns
            self.max_desc_width = int(term_cols * 0.25)
            self.pbar = tqdm.tqdm(total=len(targets),
                                  desc='building', disable=disable)
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
        
    async def _build_target(self, t: Target):
        try:
            await t.build()
        except Exception as err:
            self._diagnostics.update(gen_python_diags(err))
            raise

    async def build(self, targets: list[Target] = None):
        await self.initialize()

        if targets is None:
            targets = self.targets

        with self.context, \
             self.progress('building', targets, self._build_target, self.no_progress) as tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = list()
            for result in results:
                if isinstance(result, Exception):
                    self._logger.error(str(result))
                    errors.append(result)
            err_count = len(errors)
            if err_count == 1:
                raise errors[0]
            elif err_count > 1:
                raise asyncio.ExceptionGroup('Multiple errors occured while building the project', errors=errors)
    
    
    async def _install_target_deps(self, t: Target):
        deps_install_path = self.root.pkgs_path
        deps_settings = InstallSettings(deps_install_path)
        try:
            await load_requirements(t.requires, makefile=self.root, logger=self, install=True)

        except Exception as err:
            self._diagnostics.update(gen_python_diags(err))
            raise
    
    async def install_dependencies(self, targets: list[Target] = None):
        await self.initialize()

        if targets is None:
            targets = self.targets

        with self.context, \
             self.progress('installing deps', targets, self._install_target_deps, self.no_progress) as tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = list()
            for result in results:
                if isinstance(result, Exception):
                    self._logger.error(str(result))
                    errors.append(result)
            err_count = len(errors)
            if err_count == 1:
                raise errors[0]
            elif err_count > 1:
                raise asyncio.ExceptionGroup('Multiple errors occured while installing project dependencies', errors=errors)

    async def _install_target(self, t: Target, mode: InstallMode):
        try:
            return await t.install(self.settings.install, mode)
        except Exception as err:
            self._diagnostics.update(gen_python_diags(err))
            raise

    async def install(self, mode: InstallMode = InstallMode.user):
        await self.initialize()

        self.for_install = True
        await self.initialize()
        targets = []
        for t in self.targets:
            if t.installed:
                targets.append(t)
            else:
                self.debug('skipping %s (not marked as installed)', t.fullname)

        await self.build(targets)

        with self.context, \
             self.progress('installing', targets, functools.partial(self._install_target, mode=mode), self.no_progress) as tasks:
            installed_files = await asyncio.gather(*tasks)
            installed_files = unique(flatten(installed_files))
            manifest_path = self.settings.install.data_destination / \
                'dan' / f'{self.root.name}-manifest.txt'
            manifest_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(manifest_path, 'w') as f:
                await f.writelines([os.path.relpath(p, manifest_path.parent) + '\n' for p in installed_files])

    async def package(self, pkg_type: str, mode: InstallMode = InstallMode.user):
        import tempfile
        targets = self.targets
        if len(targets) == 1:
            base_name = targets[0].name
            version = targets[0].version
        else:
            base_name = self.root.name
        
        if not version:
            version = self.root.version

        if version:
            base_name += f'-v{version}'
            

        archive_name = f'{base_name}.{pkg_type}'

        with tempfile.TemporaryDirectory(prefix=archive_name) as tmp_dir:
            self.settings.install.destination = tmp_dir
            tmp_dir = Path(tmp_dir)
            if pkg_type.startswith('tar'):
                import tarfile
                comp_type = pkg_type.split('.')[1]
                self.info('creating %s', archive_name)
                await self.install(mode)
                with tarfile.open(archive_name, f'w:{comp_type}') as archive:
                    for it in tmp_dir.iterdir():
                        archive.add(it, arcname=it.relative_to(tmp_dir))
            elif pkg_type == 'zip':
                import zipfile
                self.info('creating %s', archive_name)
                await self.install(mode)
                with zipfile.ZipFile(archive_name, 'w') as archive:
                    for folder_name, sub_folders, file_names in os.walk(tmp_dir):
                        for filename in file_names:
                            file_path = Path(folder_name) / filename
                            archive.write(file_path, file_path.relative_to(tmp_dir))
            else:
                raise RuntimeError(f'Unhandled package type: {pkg_type}')

    @property
    def executable_targets(self) -> list[Executable]:
        return [exe for exe in self.targets if isinstance(exe, Executable)]

    async def scan_toolchains(self, script: Path = None):
        from dan.cxx.detect import create_toolchains, load_env_toolchain
        if script:
            load_env_toolchain(script)
        else:
            create_toolchains()

    async def run(self):
        await self.initialize()
        with self.context:
            results = await asyncio.gather(*[t.execute(log=True) for t in self.executable_targets])
            for result in results:
                if result[2] != 0:
                    return result[2]
        return 0

    async def _test_target(self, t: Test):
        try:
            return await t.run_test()
        except Exception as err:
            self._diagnostics.update(gen_python_diags(err))
            raise

    async def test(self):
        await self.initialize()
        tests = self.tests
        if len(tests) == 0:
            self.error('No test selected')
            return 255

        with self.context:
            with self.progress('testing', tests, self._test_target, self.no_progress) as tasks:
                results = await asyncio.gather(*tasks)
                if all(results):
                    self.info('Success !')
                    return 0
                else:
                    self.error('Failed !')
                    return 255

    async def clean(self):
        await self.initialize()
        with self.context:
            await asyncio.gather(*[t.clean() for t in self.targets])
            # from dan.cxx import target_toolchain
            # target_toolchain.compile_commands.clear()
