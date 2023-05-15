import json
import os

import aiohttp
from dan.core import aiofiles, asyncio
from dan.core.pathlib import Path
from dan.core.settings import InstallMode, InstallSettings
from dan.core.target import Target
from dan.core.find import find_files
from dan.core.version import Version, VersionSpec
from dan.core.pm import re_match
from dan.io.repositories import get_packages_path, get_repo_instance
from dan.smc.git import GitSources
from dan.smc.tar import TarSources


class PackageBuild(Target, internal=True):
    
    def __init__(self, name, version, repository, *args, spec: VersionSpec = None, **kwargs):
        self.spec = spec
        super().__init__(name, *args, version=version, **kwargs)
        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self._package_makefile = None

    @property
    def package_makefile(self):
        if self._package_makefile is None:
            from dan.core.include import load_makefile
            root = self.repo.output / 'packages' / self.name
            if (root / 'dan-requires.py').exists():
                requirements = load_makefile(root / 'dan-requires.py', f'{self.name}-requirements')
            else:
                requirements = None
            self._package_makefile = load_makefile(root / 'dan-build.py', self.name, requirements=requirements, build_path=self.build_path)
        return self._package_makefile


    async def get_available_versions(self, target: GitSources | TarSources) -> list[Version] | None:
        """Get available versions
        
        Returns the available version (if the given source's version can even be fetched) from highest to lowest.
        """
        match re_match(target.url):
            case r'.+github\.com[/:](.+?)/(.+?)/.+' as m:
                username = m[1]
                reponame = m[2]

                self.info('fetching github releases')
                url = f'https://api.github.com/repos/{username}/{reponame}/tags'
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        data = await resp.read()
                        if resp.status != 200:
                            raise RuntimeError(f'unable to fetch {url}: {data.decode()}')
                        versions = [Version(item['name']) for item in json.loads(data)]
                        versions = sorted(versions, reverse=True)
                        return versions

            case _:
                self.warning(f'cannot get available versions')

    async def __initialize__(self):
        if self.spec is not None:
            makefile = self.package_makefile
            sources = None
            for target in makefile.all_targets:
                if 'source' in target.name:
                    sources = target
                    break
            if sources is None:
                raise RuntimeError(f'Cannot find {self.name} pacakge\'s sources target')
            
            avail_versions = await self.get_available_versions(sources)
            if avail_versions is None:
                self.warning(f'unable to get available versions, default one will be used')
            else:
                for version in avail_versions:
                    if self.spec.is_compatible(version):
                        self.debug(f'using version {version} to match {self.spec}')
                        self.version = version
                        break

        packages_path = get_packages_path()
        from dan.cxx import target_toolchain as toolchain
        self.build_path = packages_path / toolchain.system / toolchain.arch / toolchain.build_type.name / self.name / str(version) / 'build'
        self.output = self.build_path / 'pymake.config.json'
        self.install_settings = InstallSettings(self.output)

        return await super().__initialize__()
    
    async def __build__(self):
        makefile = self.package_makefile
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

    def __init__(self, *args, **kwargs) -> None:
        name, spec = VersionSpec.parse(self.version)
        if spec:
            self.version = spec.version
            self.spec = spec
        else:
            self.spec = VersionSpec(Version(self.version), '=')
        if name is not None:
            self.name = name
        super().__init__(*args, **kwargs)
    
    async def __initialize__(self):
        self.pkg_build = PackageBuild(self.name,
                                      self.version,
                                      self.repository,
                                      spec=self.spec,
                                      makefile=self.makefile)
        self.dependencies.add(self.pkg_build)
        self.pkgconfig_path = self.makefile.pkgs_path / 'lib' / 'pkgconfig'
        self.dan_path = self.makefile.pkgs_path / 'lib' / 'dan'
        self.output = self.pkgconfig_path / f'{self.name}.pc'
        return await super().__initialize__()
    
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
