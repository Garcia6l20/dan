from dan.core.requirements import RequiredPackage
from dan.core.target import Target, FileDependency, Installer
from dan.core.runners import async_run
from dan.core.pm import re_match
from dan.core import aiofiles
from dan.core.find import find_executable, find_file
from dan.cxx import Toolchain

from pathlib import Path


class Project(Target, internal=True):

    cmake_targets: list[str] = None
    cmake_config_options: dict[str, str] = dict()
    cmake_options_prefix: str = None
    cmake_patch_debug_postfix: list = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmake_cache_dep = FileDependency(self.build_path / 'CMakeCache.txt')
        self.dependencies.add(self.cmake_cache_dep)
        self.toolchain : Toolchain = self.context.get('cxx_target_toolchain')
        
        cmake_options = self.cache.get('cmake_options')
        if cmake_options is not None:
            for name, default, doc in self.cache.get('cmake_options'):
                self.options.add(name, default, doc)
    
    async def _cmake(self, *cmake_args, **kwargs):
        return await async_run(['cmake', *cmake_args], logger=self, cwd=self.build_path, **kwargs, env=self.toolchain.env)

    @property
    def _target_args(self):
        targets_args = []
        if self.cmake_targets is not None:
            for target in self.cmake_targets:
                targets_args.extend(('-t', target))
        return targets_args

    async def __build__(self):
        cmake_prefix_path = {self.makefile.pkgs_path.as_posix()}
        for dep in self.dependencies:
            match dep:
                case RequiredPackage():
                    cmake_prefix_path.add(dep.makefile.pkgs_path.as_posix())
        base_opts = []
        if self.toolchain.system.startswith('msys'):
            make = find_executable(r'.+make', self.toolchain.env['PATH'].split(';'), default_paths=False)
            base_opts.extend((f'-GMinGW Makefiles', f'-DCMAKE_MAKE_PROGRAM={make.as_posix()}'))
        await self._cmake(
            self.source_path,
            *base_opts,
            f'-DCMAKE_BUILD_TYPE={self.toolchain.build_type.name.upper()}',
            f'-DCMAKE_CONFIGURATION_TYPES={self.toolchain.build_type.name.upper()}',
            f'-DCMAKE_C_COMPILER={self.toolchain.cc.as_posix()}',
            f'-DCMAKE_CXX_COMPILER={self.toolchain.cxx.as_posix()}',
            f'-DCMAKE_PREFIX_PATH={";".join(cmake_prefix_path)}',
            *[f'-D{k}={v}' for k, v in self.cmake_config_options.items()]
        )
        out, err, rc = await self._cmake('-S', self.source_path,  '-LH', log=False)
        cmake_options = list()
        doc = None
        for line in out.splitlines():
            match re_match(line.strip()):
                case r'^(.+):(\w+)=(.+)$' as m:
                    name = m[1]
                    tp = m[2]
                    value = m[3]
                    match tp:
                        case 'STRING':
                            pass
                        case 'BOOL':
                            value = value.lower() in ('on', 'true', 'yes')
                        case 'PATH'|'FILEPATH':
                            value = Path(value)
                        case _:
                            self.warning('unhandled cmake type: %s', tp)
                    if self.cmake_options_prefix is None or name.startswith(self.cmake_options_prefix):
                        # TODO: make options persistant
                        cmake_options.append((name.lower(), value, doc))
                case r'^// (.+)$' as m:
                    doc = m[1]
        self.cache['cmake_options'] = cmake_options
    
        await self._cmake('--build', '.', '--parallel', *self._target_args)
    
    async def __install__(self, installer: Installer):
        await self.build()
        await self._cmake('.', f'-DCMAKE_INSTALL_PREFIX={installer.settings.destination}')
        await self._cmake('--install', '.', *self._target_args)
        await super().__install__(installer)
        async with aiofiles.open(self.build_path / 'install_manifest.txt') as manifest_file:
            manifest = await manifest_file.readlines()
            
        if self.cmake_patch_debug_postfix is not None and self.toolchain.build_type.is_debug_mode:
            # fix: no 'd' postfix in MSVC pkgconfig
            seach_paths = [
                installer.settings.data_destination / 'pkgconfig',
                installer.settings.libraries_destination / 'pkgconfig',
            ]
            for provided in self.provides:
                pc_file = find_file(rf'{provided}\.pc', paths=seach_paths)
                self.debug('patching %s', pc_file)
                for name in self.cmake_patch_debug_postfix:
                    await aiofiles.sub(pc_file, rf'-l{name}(\s)', rf'-l{name}d\g<1>')

        installer.installed_files.extend(manifest)
