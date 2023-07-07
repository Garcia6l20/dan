from dan.core.requirements import RequiredPackage
from dan.core.target import Target, FileDependency, Installer
from dan.core.runners import async_run
from dan.core.pm import re_match
from dan.core import aiofiles
from dan.core.find import find_executable, find_file
from dan.cxx import Toolchain

import typing as t


class Project(Target, internal=True):

    cmake_targets: list[str] = None
    cmake_config_definitions: dict[str, str] = dict()
    cmake_patch_debug_postfix: list = None
    cmake_options: dict[str, tuple[str, t.Any, str]] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmake_cache_dep = FileDependency(self.build_path / 'CMakeCache.txt')
        self.dependencies.add(self.cmake_cache_dep)
        self.toolchain : Toolchain = self.context.get('cxx_target_toolchain')

    async def _cmake(self, *cmake_args, **kwargs):
        return await async_run(['cmake', *cmake_args], logger=self, cwd=self.build_path, **kwargs, env=self.toolchain.env)

    @property
    def _target_args(self):
        targets_args = []
        if self.cmake_targets is not None:
            for target in self.cmake_targets:
                targets_args.extend(('-t', target))
        return targets_args

    async def __initialize__(self):
        if self.cmake_options is not None:
            for name, (cmake_name, default, help) in self.cmake_options.items():
                opt = self.options.add(name, default, help)
                setattr(opt, 'cmake_name', cmake_name)
        return await super().__initialize__()

    async def __build__(self):
        cmake_options = dict()
        for opt in self.options:
            if hasattr(opt, 'cmake_name'):
                value = opt.value
                if isinstance(value, bool):
                    value = 'ON' if value else 'OFF'
                cmake_options[opt.cmake_name] = value

        cmake_options['CMAKE_PREFIX_PATH'] = self.makefile.root.pkgs_path.as_posix()

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
            *[f'-D{k}={v}' for k, v in self.cmake_config_definitions.items()],
            *[f'-D{k}={v}' for k, v in cmake_options.items()]
        )
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
