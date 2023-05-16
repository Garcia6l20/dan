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

    _all_builds: dict[str, 'PackageBuild'] = dict()
    
    def __init__(self, name, version, repository, *args, spec: VersionSpec = None, **kwargs):
        self.spec = spec
        super().__init__(name, *args, version=version, **kwargs)
        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self._package_makefile = None
        self._build_path = None

    @property
    def package_makefile(self):
        if self._package_makefile is None:
            from dan.core.include import load_makefile
            root = self.repo.output / 'packages' / self.name
            if (root / 'dan-requires.py').exists():
                requirements = load_makefile(root / 'dan-requires.py', f'{self.name}-requirements')
            else:
                requirements = None
            self._package_makefile = load_makefile(root / 'dan-build.py', self.name, requirements=requirements, build_path=self.build_path, parent=self.makefile)
            # self._package_makefile = load_makefile(root / 'dan-build.py', self.name, requirements=requirements, build_path=self.build_path)
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

    def get_sources(self):
        makefile = self.package_makefile
        sources = None
        for target in makefile.all_targets:
            if 'source' in target.name:
                sources = target
                break
        if sources is None:
            raise RuntimeError(f'Cannot find {self.name} pacakge\'s sources target')
        return sources

    async def __initialize__(self):
        sources = self.get_sources()
        if self.spec is not None:
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
        self._build_path = packages_path / toolchain.system / toolchain.arch / toolchain.build_type.name / self.name / str(self.version)
        self.install_settings = InstallSettings(self.build_path)
        self.output = self.install_settings.libraries_prefix
        sources.output = 'src' # TODO source_prefix in install settings

        return await super().__initialize__()
    
    @property
    def build_path(self) -> Path:
        return self._build_path
    
    async def __build__(self):
        ident = f'{self.name}-{self.version}'
        if ident in self._all_builds:
            self.debug(f'{ident} already built by {self._all_builds[ident].fullname}')
            await self._all_builds[ident].build()
            return

        self._all_builds[ident] = self

        makefile = self.package_makefile
        makefile.build_path = self.build_path / 'build'

        makefile.options.get('version').value = str(self.version)

        async with asyncio.TaskGroup(f'installing {self.name}\'s targets') as group:
            for target in makefile.all_installed:
                group.create_task(target.install(self.install_settings, InstallMode.dev))

        makefile.cache.ignore()
        del makefile

        os.chdir(self.build_path.parent)

        self.debug('cleaning')
        async with asyncio.TaskGroup(f'cleanup {self.name}') as group:
            from dan.cxx import target_toolchain as toolchain
            if not toolchain.build_type.is_debug_mode:
                group.create_task(aiofiles.rmtree(self.output / 'src'))
            # group.create_task(aiofiles.rmtree(self.build_path))


class Package(Target, internal=True):
    repository: str = 'dan.io'

    def __init__(self,
                 name: str = None,
                 version: str = None,
                 repository: str = None, **kwargs) -> None:        
        if version is not None:
            self.version = version
        match self.version:
            case str():
                _name, spec = VersionSpec.parse(self.version)
                if repository is not None:
                    self.repository = repository
                if _name is not None:
                    name = _name        
                if spec:
                    self.version = spec.version
                    self.spec = spec
                else:
                    self.spec = VersionSpec(Version(self.version), '=')
            case VersionSpec():
                self.spec = self.version
                self.version = self.spec.version
            case Version():
                self.spec = VersionSpec(Version(self.version), '=')
        if name is not None:
            self.name = name
        super().__init__(**kwargs)
    
    async def __initialize__(self):
        self.pkg_build = PackageBuild(self.name,
                                      self.version,
                                      self.repository,
                                      spec=self.spec,
                                      makefile=self.makefile)
        self.dependencies.add(self.pkg_build)
        self.pkgconfig_path = Path('pkgs') / 'lib' / 'pkgconfig'
        self.dan_path = Path('pkgs') / 'lib' / 'dan'
        self.output = self.pkgconfig_path / f'{self.name}.pc'
        return await super().__initialize__()
    
    async def __build__(self):
        self.pkgconfig_path.mkdir(exist_ok=True, parents=True)
        self.dan_path.mkdir(exist_ok=True, parents=True)      

        async with asyncio.TaskGroup(f'importing {self.name} package') as group:
            for pkg in find_files(r'.+\.pc$', [self.pkg_build.install_settings.libraries_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.pkgconfig_path))

            for pkg in find_files(r'.+\.py$', [self.pkg_build.install_settings.libraries_destination / 'dan']):
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
