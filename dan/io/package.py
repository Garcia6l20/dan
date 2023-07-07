import os

from dan.core import aiofiles, asyncio
from dan.core.pathlib import Path
from dan.core.settings import InstallMode, InstallSettings
from dan.core.target import Target
from dan.core.find import find_file, find_files
from dan.core.version import Version, VersionSpec
from dan.io.repositories import get_packages_path, get_repo_instance


class PackageBuild(Target, internal=True):
    
    def __init__(self, name, version, package, repository, *args, spec: VersionSpec = None, **kwargs):
        self.spec = spec
        self.pn = name
        super().__init__(f'{name}-build', *args, version=version, **kwargs)
        self.package = name if package is None else package
        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)
        self._package_makefile = None
        self._build_path = None
        self.toolchain = self.context.get('cxx_target_toolchain')
        self.lock: aiofiles.FileLock = None

    @property
    def package_makefile(self):
        if self._package_makefile is None:
            target = self.repo.find(self.pn, self.package)
            if target is None:
                raise RuntimeError(f'cannot find {self.pn} in {self.repo.name}')
            self._package_makefile = target.makefile
        return self._package_makefile

    def get_sources(self):
        makefile = self.package_makefile
        sources = None
        for target in makefile.all_targets:
            if 'source' in target.name:
                sources = target
                break
        if sources is None:
            raise RuntimeError(f'Cannot find {self.pn} package\'s sources target')
        return sources

    async def __initialize__(self):
        sources = self.get_sources()
        if self.spec is not None:
            avail_versions = await sources.available_versions()
            if avail_versions is None:
                self.warning(f'unable to get available versions, default one will be used')
            else:
                for version in avail_versions:
                    if self.spec.is_compatible(version):
                        self.debug(f'using version {version} to match {self.spec}')
                        self.version = version
                        break

        packages_path = get_packages_path()
        makefile = self.package_makefile

        # set package version
        version_option = makefile.options.get('version')
        if self.version is None:
            self.version = Version(version_option.value)
        else:
            version_option.value = str(self.version)

        pkgs_root = packages_path / self.toolchain.system / self.toolchain.arch / self.toolchain.build_type.name
        makefile.pkgs_path = pkgs_root / self.package / str(self.version)

        self._build_path = makefile.pkgs_path
        self.lock = aiofiles.FileLock(self.build_path / 'build.lock')

        self.install_settings = InstallSettings(self.build_path)
        
        # update package build-path
        makefile.build_path = self.build_path / 'build'


        # set our output to the last installed package
        # TODO handle multiple outputs, then set our outputs to all installed packages
        pkg_name = makefile.all_installed[-1].name     
        self.output = Path(self.install_settings.libraries_prefix) / 'pkgconfig' / f'{pkg_name}.pc'
        
        for pkg in find_files(r'.+\.pc$', [self.install_settings.libraries_destination, self.install_settings.data_destination]):
            self.output = pkg
            break

        sources.output = self.build_path / 'src' # TODO source_prefix in install settings

        return await super().__initialize__()
    
    @property
    def build_path(self) -> Path:
        return self._build_path
    
    async def __build__(self):
        if self.lock.locked:
            self.debug('package %s %s already building...', self.name, self.version)
            # wait for it
            async with self.lock:
                return

        async with self.lock:

            makefile = self.package_makefile
            build_path = makefile.build_path

            # FIXME: shall a makefile have an associated toolchain ?
            toolchain = None
            async with asyncio.TaskGroup(f'installing {self.package}\'s targets') as group:
                for target in makefile.all_installed:
                    if hasattr(target, 'toolchain'):
                        if toolchain is None:
                            toolchain = target.toolchain
                        else:
                            assert toolchain == target.toolchain, 'Toolchain missmatch'
                    group.create_task(target.install(self.install_settings, InstallMode.dev))

            makefile.cache.ignore()
            del makefile

            os.chdir(self.build_path.parent)

            self.debug('cleaning')
            async with asyncio.TaskGroup(f'cleanup {self.package}') as group:
                if toolchain is not None and not toolchain.build_type.is_debug_mode:
                    group.create_task(aiofiles.rmtree(self.output / 'src'))
                group.create_task(aiofiles.rmtree(build_path, force=True))


class Package(Target, internal=True):

    __all: dict[str, 'Package'] = dict()

    def __init__(self,
                 name: str = None,
                 version: str = None,
                 package: str = None,
                 repository: str = None, **kwargs) -> None:
        self.package = package
        self.repository = repository
        if version is not None:
            self.version = version
        if name is not None:
            self.name = name
        super().__init__(**kwargs)
        if self.name in self.__all:
            raise RuntimeError(f'duplicate package: {self.name}')
        self.__all[self.package] = self

    @classmethod
    def instance(cls, name, version, *args, package=None, **kwargs):
        if package is None:
            package = name
        if package in cls.__all:
            pkg = cls.__all[package]
            if version is not None and not version.is_compatible(pkg.version):
                raise RuntimeError(f'incompatible package version: {pkg.version} {version}')
            return pkg, False
        else:
            return Package(name, version, package, *args, **kwargs), True

    
    async def __initialize__(self):

        match self.version:
            case str():
                _name, spec = VersionSpec.parse(self.version)
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
                self.spec = VersionSpec(self.version, '=')
            case None:
                self.spec = None

        self.pkg_build = PackageBuild(self.name,
                                      self.version,
                                      self.package,
                                      self.repository,
                                      spec=self.spec,
                                      makefile=self.makefile)
        self.dependencies.add(self.pkg_build)
        lib_path = Path('pkgs') / 'lib'
        self.pkgconfig_path = lib_path / 'pkgconfig'
        self.cmake_path = lib_path / 'cmake' / self.name
        self.dan_path = lib_path / 'dan'
        
        self.output = self.pkgconfig_path / f'{self.name}.pc'

        return await super().__initialize__()
    
    async def _import_cmake_pkg(self, pkg: Path):
        self.debug('copying %s to %s', pkg, self.build_path / self.cmake_path)
        content = [
            f'set(CMAKE_CURRENT_LIST_FILE "{pkg.absolute().as_posix()}")\n',
            f'set(CMAKE_CURRENT_LIST_DIR "{pkg.parent.absolute().as_posix()}")\n'
        ]
        async with aiofiles.open(pkg) as f:
            content.extend(await f.readlines())
        dest = self.build_path / self.cmake_path / pkg.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(dest, 'w') as f:
            await f.writelines(content)

    
    async def __build__(self):
        (self.build_path / self.pkgconfig_path).mkdir(exist_ok=True, parents=True)
        (self.build_path / self.dan_path).mkdir(exist_ok=True, parents=True)
        (self.build_path / self.cmake_path).mkdir(exist_ok=True, parents=True)

        async with asyncio.TaskGroup(f'importing {self.name} package') as group:
            for pkg in find_files(r'.+\.pc$', [self.pkg_build.install_settings.libraries_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.build_path / self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.build_path / self.pkgconfig_path))

            for pkg in find_files(r'.+\.pc$', [self.pkg_build.install_settings.data_destination / 'pkgconfig']):
                self.debug('copying %s to %s', pkg, self.build_path / self.pkgconfig_path)
                group.create_task(aiofiles.copy(pkg, self.build_path / self.pkgconfig_path))

            for pkg in find_files(r'.+\.py$', [self.pkg_build.install_settings.data_destination / 'dan']):
                self.debug('copying %s to %s', pkg, self.build_path / self.dan_path)
                group.create_task(aiofiles.copy(pkg, self.build_path / self.dan_path))

            for pkg in find_files(r'.+\.cmake$', [self.pkg_build.install_settings.libraries_destination / 'cmake']):
                self.debug('copying %s to %s', pkg, self.build_path / self.cmake_path)
                group.create_task(self._import_cmake_pkg(pkg))

        if self.output.exists():
            from dan.pkgconfig.package import Data, find_package
            data = Data(self.output)
            async with asyncio.TaskGroup(f'importing {self.name} package requirements') as group:
                toolchain = self.context.get('cxx_target_toolchain')
                search_path = get_packages_path() / toolchain.system / toolchain.arch / toolchain.build_type.name
                dest = self.build_path / self.pkgconfig_path
                for pkg in data.requires:
                    pkgconfig_file = find_file(rf'{pkg.name}.pc$', [search_path])
                    # NOTE: find_package will resolve to the build-directory installed pkgconfig, wich will result in a failure
                    # pkg = find_package(pkg.name, spec=pkg.version_spec, search_paths=[search_path], makefile=self.makefile)
                    if pkgconfig_file is not None and not (dest / pkgconfig_file.name).exists():
                        self.debug('copying %s to %s', pkgconfig_file, dest)
                        group.create_task(aiofiles.copy(pkgconfig_file, dest))
