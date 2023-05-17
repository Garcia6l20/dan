import json
import aiohttp

from dan.core.version import Version
from dan.core import asyncio
from dan.src.tar import TarSources

class GitHubReleaseSources(TarSources, internal=True):

    user : str
    project : str

    @property
    def url(self):
        return self._url

    def __init__(self, *args, **kwargs):
        if self.name is None:
            self.name = f'{self.user}/{self.project}'
        super().__init__(*args, **kwargs)

    async def __initialize__(self):
        await super().__initialize__()

        self._url = self.cache.get('url')
        if self._url is None:
            avail_versions = await self.available_versions()
            if self.version is None:
                self.version = sorted(avail_versions, reverse=True)[0]
            version = self.version if isinstance(self.version, Version) else Version(self.version)
            data = avail_versions[version]
            if 'tarball_url' in data:
                self._url = data['tarball_url']
            else:
                raise RuntimeError(f'cannot resolve url of {self.name}')
            self.cache['url'] = self._url

    @asyncio.cached
    async def available_versions(self):
        self.info('fetching github releases')
        url = f'https://api.github.com/repos/{self.user}/{self.project}/tags'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
                if resp.status != 200:
                    raise RuntimeError(f'unable to fetch {url}: {data.decode()}')
                return {Version(item['name']): item for item in json.loads(data)}


