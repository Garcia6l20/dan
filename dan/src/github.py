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
            self.name = f'{self.user}-{self.project}-sources'
        super().__init__(*args, **kwargs)

    async def __initialize__(self):
        await super().__initialize__()

        self._url = self.cache.get('url')
        if self._url is None:
            avail_versions = await self.available_versions()
            if self.version is None:
                self.version = sorted(avail_versions, reverse=True)[0]
            version = self.version if isinstance(self.version, Version) else Version(self.version)
            release = avail_versions[version]
            assets = release['assets']
            # prefer assets over tarball, asset might contain submodules while tarballs will not
            for asset in assets:
                if asset['content_type'] in ('application/zip', 'application/gzip'):
                    self._url = asset['browser_download_url']
                    break
            else:
                if 'tarball_url' in release:
                    self._url = release['tarball_url']
            if self._url is None:
                raise RuntimeError(f'cannot resolve url of {self.name}')
            self.cache['url'] = self._url

    @asyncio.cached
    async def available_versions(self) -> dict[Version, dict]:
        self.info('fetching github releases')


        api_token = None

        from dan.io.repositories import _get_settings
        settings = _get_settings()
        if settings.github.api_token is not None:
            api_token = settings.github.api_token

        url = f'https://api.github.com/repos/{self.user}/{self.project}/releases'
        async with aiohttp.ClientSession() as session:
            if api_token is not None:
                session.headers['Authorization'] = f'Bearer {api_token}'
            async with session.get(url) as resp:
                data = await resp.read()
                if resp.status != 200:
                    raise RuntimeError(f'unable to fetch {url}: {data.decode()}')
                releases = json.loads(data)
                return {Version(release['tag_name']): release for release in releases}


