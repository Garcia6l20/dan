import os
from pathlib import Path
from pymake.core import aiofiles, asyncio
from pymake.core.runners import async_run
from pymake.core.settings import InstallMode, InstallSettings
from pymake.core.target import Target
from pymake.core.find import find_files
from pymake.cxx.detect import get_pymake_path
from pymake.smc.git import GitSources

class PackageRepository(Target, internal=True):

    url: str = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.output = get_pymake_path() / 'repositories' / self.name

    async def __build__(self):
        try:
            self.output.parent.mkdir()
            await async_run(f'git clone {self.url} {self.name}', logger=self, cwd=self.output.parent)
            # await async_run(f'git config advice.detachedHead off', logger=self, cwd=self.output)
            # await async_run(f'git remote add origin {self.url}', logger=self, cwd=self.output)
            # await async_run(f'git fetch -q --depth 1 origin {self.refspec}', logger=self, cwd=self.output)
            # await async_run(f'git checkout FETCH_HEAD', logger=self, cwd=self.output)

        except Exception as e:
            await aiofiles.rmtree(self.output)
            raise e
        

repositories : dict[str, dict] = {
    'pymake.io': {
        'url': 'git@github.com:Garcia6l20/pymake.io.git',
    }
}

def _get_repo_instance(repo_name:str, makefile) -> PackageRepository:
    if not repo_name in repositories:
        raise RuntimeError(f'Unknown repository: {repo_name}')
    repo_data = repositories[repo_name]
    if not 'instance' in repo_data:
        class PackageRepositoryImpl(PackageRepository, internal=True):
            name = repo_name
            url = repo_data['url']
        repo_data['instance'] = PackageRepositoryImpl(makefile=makefile)
    return repo_data['instance']

def _get_packages_path() -> Path:
    return get_pymake_path() / 'packages'

class PackageBuild(Target, internal=True):
    
    def __init__(self, name, version, repository, *args, **kwargs):
        build_path = _get_packages_path() / name / str(version)        
        super().__init__(name, *args, build_path=build_path, version=version, **kwargs)
        self.repo = _get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self.output = self.build_path / 'dist'
        # self.install_path = self.build_path / 'dist'
        self.install_settings = InstallSettings(self.output)
        self.sources = GitSources(
            name=f'{self.name}-package-sources',
            url=self.repo.url,
            refspec=f'{self.name}',
            build_path=build_path,
            makefile=self.makefile)
        self.dependencies.add(self.sources)

    async def __build__(self):
        from pymake.core.include import load_makefile
        if (self.sources.output / 'requirements.py').exists():
            requirements = load_makefile(self.sources.output / 'requirements.py', f'{self.sources.refspec}-requirements')
        else:
            requirements = None
        makefile = load_makefile(self.sources.output / 'makefile.py', self.sources.refspec, requirements=requirements, build_path=self.build_path / 'build')
        makefile.options.get('version').value = str(self.version)
        async with asyncio.TaskGroup(f'installing {self.name}\'s targets') as group:
            for target in makefile.all_installed:
                group.create_task(target.install(self.install_settings, InstallMode.dev))

        makefile.cache.ignore()
        del makefile

        os.chdir(self.build_path)
        async with asyncio.TaskGroup(f'cleanup {self.name}') as group:
            group.create_task(aiofiles.rmtree(self.build_path / 'build'))
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
            for pkg in find_files(r'.+\.pc', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.pkgconfig_path))

            for pkg in find_files(r'.+\.py', [self.pkg_build.output / self.pkg_build.install_settings.libraries_destination / 'pymake']):
                self.debug('copying %s to %s', pkg, self.pymake_path)
                group.create_task(aiofiles.copy(pkg, self.pymake_path))
        
        if self.output.exists():
            from pymake.pkgconfig.package import Data, find_package
            data = Data(self.output)
            async with asyncio.TaskGroup(f'importing {self.name} package requirements') as group:
                for pkg in data.requires:
                    pkg = find_package(pkg.name, spec=pkg.version_spec, search_paths=[_get_packages_path()])
                    self.debug('copying %s to %s', pkg.config_path, self.pkgconfig_path)
                    group.create_task(aiofiles.copy(pkg.config_path, self.pkgconfig_path))

