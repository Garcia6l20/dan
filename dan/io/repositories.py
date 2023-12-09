from pathlib import Path
from dan.core.asyncio import sync_wait
from dan.core.makefile import MakeFile

from dan.cxx.detect import get_dan_path
from dan.core.target import Target
from dan.core.runners import CommandError, async_run
from dan.core import aiofiles
from dan.core.cache import Cache

from dataclasses_json import dataclass_json
from dataclasses import dataclass, field

import typing as t


@dataclass
class RepositoryConfig:
    name: str
    url: str
    branch: str = 'main'


@dataclass
class GitHubConfig:
    api_token: t.Optional[str] = None


@dataclass_json
@dataclass
class RepositoriesSettings:
    github: GitHubConfig = field(default_factory=GitHubConfig)
    repositories: list[RepositoryConfig] = field(default_factory=lambda: [
        RepositoryConfig('dan.io', 'https://github.com/Garcia6l20/dan.io.git'),
    ])

    def get(self, name):
        for config in self.repositories:
            if config.name == name:
                return config

    @property
    def default(self):
        return self.repositories[0]


class RepositoriesConfig(Cache[RepositoriesSettings]):
    indent = 2


_repo_settings: RepositoriesConfig = None
_repo_instances: dict[str, 'PackageRepository'] = dict()


def _get_settings() -> RepositoriesSettings:
    global _repo_settings
    if _repo_settings is None:
        _repo_settings = RepositoriesConfig(
            get_dan_path() / 'repositories.json')
        if not _repo_settings.path.exists():
            sync_wait(_repo_settings.save(force=True))
    return _repo_settings.data


class PackageRepository(Target, internal=True):

    # never up-to-date
    up_to_date = False

    def __init__(self, name: RepositoryConfig, *args, **kwargs):
        self.repo_data = _get_settings().get(name)
        super().__init__(name, *args, **kwargs)
        self.output = get_dan_path() / 'repositories' / self.name
        self.toolchain = self.context.get('cxx_target_toolchain')
        self.pkgs_root = get_packages_path() / self.toolchain.system / \
            self.toolchain.arch / self.toolchain.build_type.name
        self._package_makefile = None
    
    @property
    def is_requirement(self) -> bool:
        return True

    async def __build__(self):
        if not self.output.exists():
            try:
                self.output.parent.mkdir(exist_ok=True, parents=True)
                await async_run(f'git clone -b {self.repo_data.branch} {self.repo_data.url} {self.name}', logger=self, cwd=self.output.parent)

            except Exception as e:
                await aiofiles.rmtree(self.output)
                raise e
        else:
            try:
                await async_run(f'git pull -q', logger=self, cwd=self.output)
            except CommandError:
                self.warning('cannot update %s', self.name)

    @property
    def pkgs_makefile(self) -> MakeFile:
        if self._package_makefile is None:
            from dan.core.include import load_makefile
            root = self.output / 'packages'
            with self.makefile.context:
                self._package_makefile = load_makefile(root / 'dan-build.py',
                                                       f'{self.name}.packages',
                                                       requirements=None,
                                                       build_path=self.build_path / self.name,
                                                       parent=self.makefile,
                                                       is_requirement=True)
                self._package_makefile.pkgs_path = self.pkgs_root

        return self._package_makefile

    @property
    def installed(self) -> dict[str, Target]:
        pkgs = self.pkgs_makefile
        return {f'{lib.makefile.name}:{lib.name}@{self.name}': lib for lib in pkgs.all_installed}

    def find(self, name: str, package: str) -> tuple[MakeFile, Target]:
        for lib in self.pkgs_makefile.all_installed:
            if name in lib.provides and (package is None or lib.makefile.name == package):
                return lib.makefile, lib
        return None, None


def get_repo_instance(repo_name: str, makefile=None) -> PackageRepository:
    if makefile is None:
        from dan.core.include import context
        makefile = context.root

    if repo_name is None:
        repo_name = _get_settings().default.name

    if not repo_name in _repo_instances:
        _repo_instances[repo_name] = PackageRepository(
            repo_name, makefile=makefile)
    return _repo_instances[repo_name]


def get_all_repo_instances(makefile=None) -> list[PackageRepository]:
    for repo in _get_settings().repositories:
        get_repo_instance(repo.name, makefile)
    return _repo_instances.values()


def get_packages_path() -> Path:
    return get_dan_path() / 'packages'
