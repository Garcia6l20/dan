import os
import shutil
import tempfile
from pathlib import Path
from dan.core.pathlib import Path
from dan.core import aiofiles, asyncio
from dan.core.runners import async_run
from dan.src.base import SourcesProvider
import tarfile
import zipfile

from dan.utils.net import fetch_file

class TarSources(SourcesProvider, internal=True):

    url: str
    archive_name: str = None
    extract_filter = None
    patches = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.output = str(self.name)

    async def __extract__(self, archive_path: Path, dest: Path):
        with self.progress(f'extracting {archive_path.name}', auto_update=True):
            if archive_path.suffix == '.zip':
                with zipfile.ZipFile(archive_path) as f:
                    root = os.path.commonprefix(f.namelist())
                    await asyncio.async_wait(f.extractall, dest)
            else:
                mode = 'r:*'
                if len(archive_path.suffixes) and archive_path.suffixes[-1] == '.xz':
                    mode = 'r:xz'
                with tarfile.open(archive_path, mode) as f:
                    root = None
                    def _filter(member: tarfile.TarInfo):
                        nonlocal root
                        if root is None:
                            root = member.name
                        else:
                            root = os.path.commonprefix([root, member.name])
                        if self.extract_filter is None:
                            return member
                        else:
                            return self.extract_filter(member, dest / member.name)
                    members = []
                    for m in f:
                        m = _filter(m)
                        if m:
                            members.append(m)
                    self.debug('extracting %d members', len(members))
                    await asyncio.async_wait(f.extractall, dest, members)
        return root

    async def __build__(self):
        archive_name = self.archive_name or self.url.split("/")[-1]
        archive_path = self.build_path / archive_name
        if archive_path.exists():
            self.debug('%s already available (download skipped)', archive_path)
        else:
            self.info(f'downloading {self.url}')
            await fetch_file(self.url, self.build_path / archive_name, self.name, progress=self.progress)
        with tempfile.TemporaryDirectory(prefix=f'{self.name}-') as tmp_dest:
            extract_dest = Path(tmp_dest) / 'a'
            self.info(f'extracting {archive_name}')
            root = await self.__extract__(archive_path, extract_dest)
            await asyncio.get_event_loop().run_in_executor(None, shutil.move, extract_dest / root, self.output)
            
            if self.patches is not None:
                for patch in self.patches:
                    self.info('applying %s', patch)
                    await async_run(['bash', '-c', 'cd', self.output , '&&', 'patch', '-p0', '<', self.source_path / patch], logger=self, cwd=self.output)

            await aiofiles.os.remove(archive_path)
