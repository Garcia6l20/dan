
from pymake import pkgconfig
from pymake.core import asyncio
from pymake.core.include import MakeFile
from pymake.core.settings import InstallMode, InstallSettings
from pymake.cxx.targets import LibraryType


class LocalPackage(pkgconfig.Package):
    _settings = InstallSettings()

    def __init__(self, makefile: MakeFile) -> None:
        from pymake.core.include import context
        self._settings.destination = context.root.build_path / 'pkgs'
        name = makefile.name
        super().__init__(name, config_path=self._settings.libraries_destination /
                         'pkgconfig' / f'{name}.pc')
        self.makefile = makefile
        self.output = self.config_path

    @asyncio.once_method
    async def preload(self):

        for target in self.makefile.installed_targets:
            self.load_dependencies(target.dependencies)

        await asyncio.gather(*[dep.preload() for dep in self.dependencies])

        if not self.up_to_date:
            for target in self.makefile.installed_targets:
                await target.install(self._settings, InstallMode.dev)
        await super().preload(recursive_once=True)

    @asyncio.once_method
    async def install(self, settings: InstallSettings, mode: InstallMode):
        return await super().install(settings, mode, recursive_once=True)

    @property
    def up_to_date(self):
        return self.output.exists()
