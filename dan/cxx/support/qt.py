
from dan.core import aiofiles, asyncio
from dan.core.find import find_executable
from dan.core.pathlib import Path
from dan.core.runners import async_run
from dan.cxx.targets import CXXObject, Executable, Library, CXXObjectsTarget
from dan.pkgconfig.package import Package


class _QtMoccer:
    
    async def __initialize__(self):
        qt_core = Package('Qt5Core', makefile=self.makefile)
        await qt_core.initialize()
        self.moc = self.makefile.cache.get('moc_executable')
        if not self.moc:
            self.moc = find_executable(
                'moc', paths=[qt_core.host_bins], default_paths=False)
            self.makefile.cache.moc_executable = str(self.moc)
        self.dependencies.add(qt_core)

        self.includes.private.append(self.build_path)

        for module in self.qt_modules:
            pkg = Package(f'Qt5{module}', makefile=self.makefile)
            await pkg.initialize()
            self.dependencies.add(pkg)

        mocs = self.cache.get('mocs', list())
        for moc_name in mocs:
            moc_path = self.build_path / moc_name
            self.objs.append(
                CXXObject(moc_path, self))
            self.other_generated_files.add(moc_path)

        await super().__initialize__()

    async def __clean__(self):
        await super().__clean__()
        self.cache.reset('mocs')

    async def __build__(self):

        mocs = list()
        moc_objs = list()

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
                            moc_objs.append(
                                CXXObject(moc_file_path, self))
                            mocs.append(moc_name)

        # we have to generate objects first in order to get files dependencies,
        # which are used later to moc those dependencies (whenever they are within the same source directory)

        # build existing objects
        await CXXObjectsTarget.__build__(self)

        # generate moc source files
        async with asyncio.TaskGroup(f'moccing {self.name}') as g:
            sources = set()
            for obj in self.objs:
                for dep in [Path(dep) for dep in obj.cache['deps']]:
                    if self.source_path in dep.parents:
                        sources.add(dep)
            for source in sources:
                g.create_task(do_moc(source))
        
        # add moc sources to objects dependencies
        self.objs.extend(moc_objs)

        # update cache
        self.cache['mocs'] = mocs

        # continue parent build process
        await super().__build__()


def moc(modules: list[str]):
    def decorator(cls):
        from dan.core.include import context
        @context.current.wraps(cls)
        class QtWapped(_QtMoccer, cls):
            qt_modules = modules
        return cls
    return decorator
