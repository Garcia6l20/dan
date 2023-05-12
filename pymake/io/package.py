import os
from pymake.core import aiofiles, asyncio
from pymake.core.settings import InstallMode, InstallSettings
from pymake.core.target import Target
from pymake.core.find import find_files
from pymake.io.repositories import get_packages_path, get_repo_instance
from pymake.smc.git import GitSources
from pymake.smc.tar import TarSources


class PackageBuild(Target, internal=True):
    
    def __init__(self, name, version, repository, *args, **kwargs):
        packages_path = get_packages_path()
        from pymake.cxx import target_toolchain as toolchain
        build_path = packages_path / toolchain.system / toolchain.arch / toolchain.build_type.name / name / str(version) / 'data'
        super().__init__(name, *args, build_path=build_path, version=version, **kwargs)
        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self.output = self.build_path.parent
        self.install_settings = InstallSettings(self.output)
        self.sources = GitSources(
            name=f'{self.name}-package-sources',
            url=self.repo.url,
            refspec=f'{self.name}',
            build_path=build_path,
            makefile=self.makefile,
            dirname='package-sources')
        self.dependencies.add(self.sources)

    async def __build__(self):
        from pymake.core.include import load_makefile
        if (self.sources.output / 'requirements.py').exists():
            requirements = load_makefile(self.sources.output / 'requirements.py', f'{self.sources.refspec}-requirements')
        else:
            requirements = None
        makefile = load_makefile(self.sources.output / 'makefile.py', self.sources.refspec, requirements=requirements, build_path=self.build_path)
        makefile.options.get('version').value = str(self.version)

        async with asyncio.TaskGroup(f'installing {self.name}\'s targets') as group:
            for target in makefile.all_installed:
                group.create_task(target.install(self.install_settings, InstallMode.dev))

        makefile.cache.ignore()
        del makefile

        os.chdir(self.build_path)
        async with asyncio.TaskGroup(f'cleanup {self.name}') as group:
            from pymake.cxx import target_toolchain as toolchain
            if toolchain.build_type.is_debug:
                # In debug mode we keep sources in order to let it be resolvable by debuggers
                for file in self.build_path.iterdir():
                    if file.is_file():
                        group.create_task(aiofiles.os.remove(file))
            else:
                group.create_task(aiofiles.rmtree(self.build_path))
                # FIXME: access denied in .git/objects
                # group.create_task(aiofiles.rmtree(self.build_path / 'sources'))


class Package(Target, internal=True):
    repository: str = 'pymake.io'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pkg_build = PackageBuild(self.name,
                                      self.version,
                                      self.repository,
                                      makefile=self.makefile)
        self.dependencies.add(self.pkg_build)
        self.pkgconfig_path = self.makefile.pkgs_path / 'lib' / 'pkgconfig'
        self.pymake_path = self.makefile.pkgs_path / 'lib' / 'pymake'
        self.output = self.pkgconfig_path / f'{self.name}.pc'
    
    async def __build__(self):
        self.pkgconfig_path.mkdir(exist_ok=True, parents=True)
        self.pymake_path.mkdir(exist_ok=True, parents=True)

        async with asyncio.TaskGroup(f'importing {self.name} package') as group:
            for pkg in find_files(r'.+\.pc$', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.pkgconfig_path))

            for pkg in find_files(r'.+\.py$', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'pymake']):
                self.debug('copying %s to %s', pkg, self.pymake_path)
                group.create_task(aiofiles.copy(pkg, self.pymake_path))
        
        if self.output.exists():
            from pymake.pkgconfig.package import Data, find_package
            data = Data(self.output)
            async with asyncio.TaskGroup(f'importing {self.name} package requirements') as group:
                for pkg in data.requires:
                    pkg = find_package(pkg.name, spec=pkg.version_spec, search_paths=[get_packages_path()])
                    self.debug('copying %s to %s', pkg.config_path, self.pkgconfig_path)
                    group.create_task(aiofiles.copy(pkg.config_path, self.pkgconfig_path))
