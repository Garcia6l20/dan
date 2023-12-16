from pathlib import Path
from dan.core.settings import InstallMode, InstallSettings
from dan.core.target import Target, FileDependency, Installer
from dan.core.runners import async_run
from dan.core import aiofiles, asyncio
from dan.core.find import find_file
from dan.cxx import Toolchain

import typing as t
import os

import platform

async def get_ninja(progress):
    from dan.cxx.detect import get_dan_path
    match platform.system():
        case 'Windows':
            suffix = '.exe'
        case _:
            suffix = ''
    bin_path = get_dan_path() / 'os-utils' / 'bin'
    ninja_path = bin_path / f'ninja{suffix}'
    ninja_version = '1.11.1'
    if not ninja_path.exists():
        match platform.system():
            case 'Windows':
                name = 'ninja-win'
            case 'Linux':
                name = 'ninja-linux'
            case 'Darwin':
                name = 'ninja-mac'
        import tempfile
        import zipfile
        import stat
        from dan.utils.net import fetch_file
        with tempfile.TemporaryDirectory(prefix=f'dan-ninja-') as tmp_dest:
            tmp_dest = Path(tmp_dest)
            archive_name = f'{name}.zip'
            await fetch_file(f'https://github.com/ninja-build/ninja/releases/download/v{ninja_version}/{archive_name}', tmp_dest / archive_name, progress=progress)
            with zipfile.ZipFile(tmp_dest / archive_name) as f:
                f.extractall(bin_path)
            ninja_path.chmod(ninja_path.stat().st_mode | stat.S_IEXEC)
    return ninja_path



class Project(Target, internal=True):

    cmake_targets: list[str] = None
    cmake_config_definitions: dict[str, str] = dict()
    cmake_patch_debug_postfix: list = None
    cmake_options: dict[str, tuple[str, t.Any, str]] = None
    cmake_generator: str = 'Ninja'
    cmake_subdirectory: str = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmake_cache_dep = FileDependency(self.build_path / 'CMakeCache.txt')
        self.dependencies.add(self.cmake_cache_dep)
        self.toolchain : Toolchain = self.context.get('cxx_target_toolchain')
        self.__env = None

    def get_env(self):
        if self.__env is None:
            env = self.toolchain.env
            from dan.cxx.detect import get_dan_path
            epath = env.get('PATH', os.environ['PATH']).split(os.pathsep)
            epath.insert(0, str(get_dan_path() / 'os-utils' / 'bin'))
            env['PATH'] = os.pathsep.join(epath)
            self.__env = env
        return self.__env


    async def _cmake(self, *cmake_args, **kwargs):
        return await async_run(['cmake', *cmake_args], logger=self, cwd=self.build_path, **kwargs, env=self.get_env())

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
        if self.cmake_generator.startswith('Ninja'):
            ninja = await get_ninja(self.progress)
            base_opts.extend((f'-G{self.cmake_generator}', f'-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}'))
        else:
            raise RuntimeError('Only Ninja generators are currently supported')
        
        if 'multi' in self.cmake_generator.lower():
            base_opts.append(f'-DCMAKE_CONFIGURATION_TYPES={self.toolchain.build_type.name.title()}')
        else:
            base_opts.append(f'-DCMAKE_BUILD_TYPE={self.toolchain.build_type.name.title()}')

        source_path = self.source_path
        if self.cmake_subdirectory:
            source_path /= self.cmake_subdirectory

        await self._cmake(
            source_path,
            *base_opts,
            f'-DCMAKE_C_COMPILER={self.toolchain.cc.as_posix()}',
            f'-DCMAKE_CXX_COMPILER={self.toolchain.cxx.as_posix()}',
            *[f'-D{k}={v}' for k, v in self.cmake_config_definitions.items()],
            *[f'-D{k}={v}' for k, v in cmake_options.items()]
        )
        await self._cmake('--build', '.', '--parallel', *self._target_args)
    
    @asyncio.cached(unique = True)
    async def install(self, settings: InstallSettings, mode: InstallMode):
        self.cmake_config_definitions['CMAKE_INSTALL_PREFIX'] = settings.destination
        return await super().install(settings, mode)

    async def __install__(self, installer: Installer):
        await self._cmake('--install', '.')

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
