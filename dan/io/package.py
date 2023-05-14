import os
from dan.core import aiofiles, asyncio
from dan.core.settings import InstallMode, InstallSettings
from dan.core.target import Target
from dan.core.find import find_files
from dan.io.repositories import get_packages_path, get_repo_instance


class PackageBuild(Target, internal=True):
    
    def __init__(self, name, version, repository, *args, **kwargs):
        packages_path = get_packages_path()
        from dan.cxx import target_toolchain as toolchain
        build_path = packages_path / toolchain.system / toolchain.arch / toolchain.build_type.name / name / str(version) / 'build'
        super().__init__(name, *args, build_path=build_path, version=version, **kwargs)
        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self.output = self.build_path.parent
        self.install_settings = InstallSettings(self.output)

    async def __build__(self):
        from dan.core.include import load_makefile
        root = self.repo.output / 'packages' / self.name
        if (root / 'dan-requires.py').exists():
            requirements = load_makefile(root / 'dan-requires.py', f'{self.name}-requirements')
        else:
            requirements = None
        makefile = load_makefile(root / 'dan-build.py', self.name, requirements=requirements, build_path=self.build_path)
        makefile.options.get('version').value = str(self.version)

        async with asyncio.TaskGroup(f'installing {self.name}\'s targets') as group:
            for target in makefile.all_installed:
                group.create_task(target.install(self.install_settings, InstallMode.dev))

        makefile.cache.ignore()
        del makefile

        os.chdir(self.build_path)
        async with asyncio.TaskGroup(f'cleanup {self.name}') as group:
            from dan.cxx import target_toolchain as toolchain
            if toolchain.build_type.is_debug_mode:
                # In debug mode we keep sources in order to let it be resolvable by debuggers
                for file in self.build_path.iterdir():
                    if file.is_file():
                        group.create_task(aiofiles.os.remove(file))
            else:
                group.create_task(aiofiles.rmtree(self.build_path))
                # FIXME: access denied in .git/objects
                # group.create_task(aiofiles.rmtree(self.build_path / 'sources'))


class Package(Target, internal=True):
    repository: str = 'dan.io'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pkg_build = PackageBuild(self.name,
                                      self.version,
                                      self.repository,
                                      makefile=self.makefile)
        self.dependencies.add(self.pkg_build)
        self.pkgconfig_path = self.makefile.pkgs_path / 'lib' / 'pkgconfig'
        self.dan_path = self.makefile.pkgs_path / 'lib' / 'dan'
        self.output = self.pkgconfig_path / f'{self.name}.pc'
    
    async def __build__(self):
        self.pkgconfig_path.mkdir(exist_ok=True, parents=True)
        self.dan_path.mkdir(exist_ok=True, parents=True)

        async with asyncio.TaskGroup(f'importing {self.name} package') as group:
            for pkg in find_files(r'.+\.pc$', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.pkgconfig_path))

            for pkg in find_files(r'.+\.py$', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'dan']):
                self.debug('copying %s to %s', pkg, self.dan_path)
                group.create_task(aiofiles.copy(pkg, self.dan_path))
        
        if self.output.exists():
            from dan.pkgconfig.package import Data, find_package
            data = Data(self.output)
            async with asyncio.TaskGroup(f'importing {self.name} package requirements') as group:
                for pkg in data.requires:
                    pkg = find_package(pkg.name, spec=pkg.version_spec, search_paths=[get_packages_path()])
                    self.debug('copying %s to %s', pkg.config_path, self.pkgconfig_path)
                    group.create_task(aiofiles.copy(pkg.config_path, self.pkgconfig_path))
