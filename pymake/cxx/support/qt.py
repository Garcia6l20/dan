
from pymake.core import aiofiles, asyncio
from pymake.core.find import find_executable
from pymake.core.pathlib import Path
from pymake.core.runners import async_run
from pymake.cxx.targets import CXXObject, Executable, Library
from pymake.pkgconfig.package import Package


class _QtMoccer:
    
    async def __initialize__(self):
        qt_core = Package('Qt5Core')
        await qt_core.initialize()
        self.moc = self.makefile.cache.get('moc_executable')
        if not self.moc:
            self.moc = find_executable(
                'moc', paths=[qt_core.host_bins], default_paths=False)
            self.makefile.cache.moc_executable = str(self.moc)
        self.load_dependency(qt_core)

        self.includes.private.append(self.build_path)

        for module in self.qt_modules:
            pkg = Package(f'Qt5{module}')
            await pkg.initialize()
            self.load_dependency(pkg)

        mocs = self.cache.get('mocs', list())
        for moc_name in mocs:
            moc_path = self.build_path / moc_name
            self.objs.append(
                CXXObject(f'{self.name}.{moc_name}', self, moc_path))
            self.other_generated_files.add(moc_path)

        await super().__initialize__()

    async def __clean__(self):
        await super().__clean__()
        self.cache.reset('mocs')

    async def __build__(self):

        mocs = self.cache.get('mocs', list())

        async def do_moc(file: Path):
            moc_name = file.with_suffix('.moc.cpp').name
            moc_file_path = self.build_path / moc_name
            if not moc_file_path.exists() or file.younger_than(moc_file_path):
                if moc_file_path.exists():
                    self.info(f'updating {moc_file_path}')
                else:
                    self.info(f'generating {moc_file_path}')
                out, err, rc = await async_run([self.moc, *self.includes.private, *self.compile_definitions.private, file], logger=self, log=False)
                if rc == 0 and len(out):
                    async with aiofiles.open(moc_file_path, 'w') as f:
                        await f.write(out)
                        if not moc_name in mocs:
                            self.objs.append(
                                CXXObject(f'{self.name}.{moc_name}', self, moc_file_path))
                            mocs.append(moc_name)

        mocings = list()
        for header in self.headers:
            mocings.append(do_moc(header))
        await asyncio.gather(*mocings)
        await super().__build__()


class QtExecutable(_QtMoccer, Executable, internal=True):
    def __init__(self, name: str, *args, qt_modules: list[str] = list(), **kwargs):
        Executable.__init__(self, name, *args, **kwargs)
        self.qt_modules = qt_modules


class QtLibrary(_QtMoccer, Library, internal=True):
    def __init__(self, name: str, *args, qt_modules: list[str] = list(), **kwargs):
        Library.__init__(self, name, *args, **kwargs)
        self.qt_modules = qt_modules
