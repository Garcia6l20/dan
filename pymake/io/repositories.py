from pathlib import Path

from pymake.cxx.detect import get_pymake_path
from pymake.core.target import Target
from pymake.core.runners import async_run
from pymake.core import aiofiles

class PackageRepository(Target, internal=True):

    url: str = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.output = get_pymake_path() / 'repositories' / self.name

    async def __build__(self):
        try:
            self.output.parent.mkdir(exist_ok=True, parents=True)
            await async_run(f'git clone --mirror {self.url} {self.name}', logger=self, cwd=self.output.parent)

        except Exception as e:
            await aiofiles.rmtree(self.output)
            raise e


repositories : dict[str, dict] = {
    'pymake.io': {
        'url': 'https://github.com/Garcia6l20/pymake.io.git',
    }
}

def get_repo_instance(repo_name:str, makefile) -> PackageRepository:
    if not repo_name in repositories:
        raise RuntimeError(f'Unknown repository: {repo_name}')
    repo_data = repositories[repo_name]
    if not 'instance' in repo_data:
        class PackageRepositoryImpl(PackageRepository, internal=True):
            name = repo_name
            url = repo_data['url']
        repo_data['instance'] = PackageRepositoryImpl(makefile=makefile)
    return repo_data['instance']

def get_packages_path() -> Path:
    return get_pymake_path() / 'packages'
