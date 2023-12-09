import os
import re

from dan.core import aiofiles, asyncio
from dan.core.pathlib import Path
from dan.core.settings import InstallMode, InstallSettings
from dan.core.target import Target
from dan.core.find import find_file, find_files
from dan.core.version import Version, VersionSpec
from dan.io.repositories import get_packages_path, get_repo_instance
from dan.src.base import SourcesProvider


class PackageBuild(Target, internal=True):

    inherits_version = False
    
    def __init__(self, name, version, repository, package_makefile, *args, spec: VersionSpec = None, **kwargs):
        self.spec = spec
        self.pn = name
        super().__init__(name, *args, version=version, **kwargs)
        self.repo = repository
        self.preload_dependencies.add(self.repo)
        self.package_makefile = package_makefile
        self._build_path = None
        self.toolchain = self.context.get('cxx_target_toolchain')
        self.lock: aiofiles.FileLock = None
        self.__up_to_date = True

    @property
    def is_requirement(self) -> bool:
        return True
    
    @property
    def sources_targets(self):
        targets = []
        for target in self.package_makefile.all_installed:
            for dep in target.preload_dependencies.all:
                if isinstance(dep, SourcesProvider):
                    targets.append(dep)
        return targets
    
    @property
    def target(self):
        if self._target is None:
            self.__resolve()
        return self._target

    async def __initialize__(self):
        source_targets = self.sources_targets
        sources = source_targets[0]
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
        makefile.pkgs_path = pkgs_root / self.name / str(self.version)
        src_path = packages_path / 'src' / self.name / str(self.version)

        self._build_path = makefile.pkgs_path
        self.lock = aiofiles.FileLock(self.build_path / 'build.lock')

        self.install_settings = InstallSettings(self.build_path)
        
        # update package build-path
        makefile.build_path = self.build_path / 'build'
        
        for target in self.package_makefile.all_installed:
            for provided in target.provides:
                pkg_file = find_file(rf'(lib)?{provided}.pc', [self.install_settings.libraries_destination, self.install_settings.data_destination], re.IGNORECASE)
                if pkg_file is None:
                    self.__up_to_date = False
                    break

        for target in self.package_makefile.all_installed:
            for source_target in target.preload_dependencies.all:
                if isinstance(source_target, SourcesProvider):
                    source_target.output = src_path
                    if target.subdirectory is not None:
                        source_target.output /= target.subdirectory

        return await super().__initialize__()
    
    @property
    def up_to_date(self):
        return self.__up_to_date
    
    @property
    def build_path(self) -> Path:
        return self._build_path
    
    async def __build__(self):
        if self.lock.locked:
            self.info('package %s %s is locked, waiting for it to be released...', self.name, self.version)
            # wait for it
            async with self.lock:
                if self.up_to_date:
                    return

        async with self.lock:

            makefile = self.package_makefile
            build_path = makefile.build_path

            async with asyncio.TaskGroup(f'downloading {self.name} sources') as g:
                for target in self.sources_targets:
                    g.create_task(target.build())

            installed = set()
            async def install_target(target):
                if target in installed:
                    return
                installed.add(target)
                for dep in target.target_dependencies:
                    if dep.installed and dep.makefile == self.package_makefile:
                        await install_target(dep)

                self.info(f'installing {target.name}')
                await target.install(self.install_settings, InstallMode.dev)

            async with asyncio.TaskGroup(f'installing {self.name} targets') as g:
                for target in makefile.all_installed:
                    if target in installed:
                        continue
                    g.create_task(install_target(target))

            makefile.cache.ignore()
            del makefile

            os.chdir(self.build_path.parent)

            if not self.toolchain.build_type.is_debug_mode:
                # in debug mode we keep build directory in order to keep debug symbols (might be changed in the future)
                self.debug('cleaning')
                async with asyncio.TaskGroup(f'cleanup {self.name}') as group:
                    group.create_task(aiofiles.rmtree(build_path, force=True))

class ReusePackage(BaseException):
    def __init__(self, pkg):
        self.pkg = pkg

class IoPackage(Target, internal=True):
    
    inherits_version = False

    __all: dict[str, 'IoPackage'] = dict()

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

        self.repo = get_repo_instance(repository, self.makefile)
        self.preload_dependencies.add(self.repo)

    @property
    def is_requirement(self) -> bool:
        return True

    def find(self, name):
        for t in self.package_makefile.all_installed:
            if t.name == name or name in t.provides:
                return t

    @classmethod
    async def instance(cls, name, version, *args, package=None, **kwargs):

        for _, pkg in cls.__all.items():
            if pkg.name == package:
                if version is not None and not version.is_compatible(pkg.version):
                    raise RuntimeError(f'incompatible package version: {pkg.version} {version}')
                return pkg, False
            else:
                target = pkg.find(name)
                if target is not None:
                    if version is not None and not version.is_compatible(pkg.version):
                        raise RuntimeError(f'incompatible package version: {pkg.version} {version}')
                    return pkg, False

        try:
            pkg = IoPackage(name, version, package, *args, **kwargs)
            await pkg.initialize()
            return pkg, True
        except ReusePackage as reuse:
            # concurrent package initialization
            return reuse.pkg, False

    
    async def __initialize__(self):

        self.package_makefile, self.target = self.repo.find(self.name, self.package)
        if self.target is None:
            raise RuntimeError(f'cannot find {self.name} in {self.repo.name}')
        if self.package is None:
            self.package = self.package_makefile.name

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

        if self.package in self.__all:
            other = self.__all[self.package]
            await other.initialize()
            if self.spec is not None and not self.spec.is_compatible(other.version):
                raise RuntimeError(f'duplicate package with incompatible version detected: {self.package} ({self.version} vs {other.version})')
            if self.version is not None and self.version != other.version:
                self.warning(f'using {other.version} instead of {self.version}')
            raise ReusePackage(other)

        self.__all[self.package] = self

        self.pkg_build = PackageBuild(self.package,
                                      self.version,
                                      self.repo,
                                      self.package_makefile,
                                      spec=self.spec,
                                      parent=self)
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
            from dan.pkgconfig.package import Data
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
