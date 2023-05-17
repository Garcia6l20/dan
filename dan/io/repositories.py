from pathlib import Path
from dan.core.asyncio import sync_wait

from dan.cxx.detect import get_dan_path
from dan.core.target import Target
from dan.core.runners import async_run
from dan.core import aiofiles
from dan.core.cache import Cache

from dataclasses_json import dataclass_json
from dataclasses import dataclass, field


@dataclass
class RepositoryConfig:
    name: str
    url: str
    branch: str = 'main'


@dataclass_json
@dataclass
class RepositoriesSettings:
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
_repo_instances : dict[str, 'PackageRepository'] = dict()

def _get_settings():
    global _repo_settings
    if _repo_settings is None:
        _repo_settings = RepositoriesConfig(get_dan_path() / 'repositories.json')
        if not _repo_settings.path.exists():
            sync_wait(_repo_settings.save(force=True))
    return _repo_settings.data


class PackageRepository(Target, internal=True):

    # never up-to-date
    up_to_date = False

    def __init__(self, name : RepositoryConfig, *args, **kwargs):
        self.repo_data = _get_settings().get(name)
        super().__init__(name, *args, **kwargs)
        self.output = get_dan_path() / 'repositories' / self.name

    async def __build__(self):
        if not self.output.exists():
            try:
                self.output.parent.mkdir(exist_ok=True, parents=True)
                await async_run(f'git clone -b {self.repo_data.branch} {self.repo_data.url} {self.name}', logger=self, cwd=self.output.parent)

            except Exception as e:
                await aiofiles.rmtree(self.output)
                raise e
        else:
                await async_run(f'git pull', logger=self, cwd=self.output)


def get_repo_instance(repo_name:str, makefile) -> PackageRepository:
    if repo_name is None:
        repo_name = _get_settings().default.name

    if not repo_name in _repo_instances:
        _repo_instances[repo_name] = PackageRepository(repo_name, makefile=makefile)
    return _repo_instances[repo_name]

def get_packages_path() -> Path:
    return get_dan_path() / 'packages'
