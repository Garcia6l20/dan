from dan.core import aiofiles
from dan.core.find import find_executable
from dan.core.pathlib import Path
from dan.core.runners import async_run
from dan.cxx.targets import CXXObject
from dan.core.target import Target
from dan.pkgconfig.package import find_package


class _UIObject(Target, internal=True):

    def __init__(self, ui_file: Path, parent, *args, **kwargs) -> None:
        self.ui_file = Path(ui_file)
        name = 'ui_' + self.ui_file.with_suffix('.h').name
        super().__init__(name, parent, *args, **kwargs)
        self.output = self.ui_file.with_name(name)
        if not self.ui_file.is_absolute():
            self.ui_file = self.source_path / self.ui_file
        self.dependencies.add(self.ui_file)
        

    async def __build__(self):
        p = self.parent
        self.output.parent.mkdir(exist_ok=True, parents=True)
        await async_run([p.uic, '-o', self.output,  self.ui_file], logger=p, log=False, cwd=self.build_path, env=self.toolchain.env)

class _RCCObject(CXXObject, internal=True):

    def __init__(self, resource_file: Path, parent, *args, **kwargs) -> None:
        self.resource_file = Path(resource_file)
        name = 'rcc_' + self.resource_file.with_suffix('.cpp').name
        super().__init__(parent.build_path / self.resource_file.with_name(name), parent, *args, **kwargs)
        if not self.resource_file.is_absolute():
            self.resource_file = self.source_path / self.resource_file
        self.dependencies.add(self.resource_file)

    async def __build__(self):
        p = self.parent
        out, err, rc = await async_run([p.rcc, self.resource_file], logger=p, log=False, cwd=self.build_path, env=self.toolchain.env)
        async with aiofiles.open(self.source, 'w') as f:
            await f.write(out)

        await super().__build__()

class _MocSource(Target, internal=True):

    def __init__(self, header_file: Path, parent, *args, **kwargs) -> None:
        self.header_file = Path(header_file)
        name = 'moc_' + self.header_file.with_suffix('.cpp').name
        source_file = self.header_file.with_name(name)
        if source_file.is_absolute():
            source_file = source_file.relative_to(parent.source_path)
        super().__init__(name, parent, *args, **kwargs)
        self.output = source_file
        self.dependencies.add(self.header_file)

    async def __build__(self):
        p = self.parent
        self.output.parent.mkdir(parents=True, exist_ok=True)
        await async_run([p.moc, '-o', self.output,  self.header_file], logger=p, log=False, cwd=self.build_path, env=self.toolchain.env)

class _MocObject(CXXObject, internal=True):

    def __init__(self, header_file: Path, parent, *args, **kwargs) -> None:
        self.header_file = Path(header_file)
        name = 'moc_' + self.header_file.with_suffix('.cpp').name
        source_file = self.header_file.with_name(name)
        if source_file.is_absolute():
            source_file = source_file.relative_to(parent.source_path)
        super().__init__(parent.build_path / source_file, parent, *args, **kwargs)
        if not self.header_file.is_absolute():
            self.header_file = self.source_path / self.header_file
        self.dependencies.add(self.header_file)

    async def __build__(self):
        p = self.parent
        self.source.parent.mkdir(parents=True, exist_ok=True)
        await async_run([p.moc, '-o', self.source,  self.header_file], logger=p, log=False, cwd=self.build_path, env=self.toolchain.env)
        await super().__build__()

class _Wrapper:
    
    async def __initialize__(self):
        qt_core =  find_package(f'Qt{self.qt_major}Core', makefile=self.makefile)
        await qt_core.initialize()
        
        _search_paths = None
        def get_search_path():
            nonlocal _search_paths
            if _search_paths is None:
                _search_paths = [qt_core.host_bins if hasattr(qt_core, 'host_bins') else qt_core.bindir, qt_core.prefix]
            return _search_paths
        
        self.moc = self.makefile.cache.get('moc_executable')
        if not self.moc:
            self.moc = find_executable(
                'moc', paths=get_search_path(), default_paths=False)
            self.makefile.cache.moc_executable = str(self.moc)

        self.rcc = self.makefile.cache.get('rcc_executable')
        if not self.rcc:
            self.rcc = find_executable(
                'rcc', paths=get_search_path(), default_paths=False)
            self.makefile.cache.rcc_executable = str(self.rcc)
            
        self.uic = self.makefile.cache.get('uic_executable')
        if not self.uic:
            self.uic = find_executable(
                'uic', paths=get_search_path(), default_paths=False)
            self.makefile.cache.uic_executable = str(self.uic)

        self.dependencies.add(qt_core)

        self.includes.private.append(self.build_path)

        for module in self.qt_modules:
            pkg = find_package(f'Qt{self.qt_major}{module}', makefile=self.makefile)
            await pkg.initialize()
            self.dependencies.add(pkg)

        extra_include_paths = set()
        for ui_file in self.qt_ui_files:
            uio = _UIObject(ui_file, self)
            self.dependencies.add(uio)
            extra_include_paths.add(uio.output.parent.as_posix())
        
        for resource_file in self.qt_resource_files:
            rcco = _RCCObject(resource_file, self)
            self.objs.append(rcco)
            extra_include_paths.add(rcco.source.parent.as_posix())

        self.includes.extend(extra_include_paths, private=True)

        super()._init_sources()

        prev_objs = list(self.objs)

        self.moc_sources = self.cache.get('moc_sources', list())
        if self.qt_build_moc:
            for file in self.moc_sources:
                self.objs.append(_MocObject(file, self))

        await super().__initialize__()

        if not self.up_to_date:
            if self.qt_build_moc:
                self.objs = prev_objs
            
            self.moc_sources = list()
            from dan.core.find import find_files
            search_paths = set()
            for p in self.includes.all_raw:
                if self.source_path == p or self.source_path in p.parents:
                    search_paths.add(p)
            self.debug('looking for source files to moc in: %s', ', '.join([p.as_posix() for p in search_paths]))
            for file in find_files('.+\.h\w*', search_paths):
                out, err, rc = await async_run([self.moc, file], logger=None, log=False, cwd=self.build_path, no_raise=True, env=self.toolchain.env)
                if rc != 0 or len(out) == 0:
                    self.debug('skipping %s: %s%s', file.name, out, err)
                    continue
                self.moc_sources.append(file)
                if self.qt_build_moc:
                    self.objs.append(_MocObject(file, self))
                else:
                    self.dependencies.add(_MocSource(file, self))
            self.cache['moc_sources'] = self.moc_sources
        elif not self.qt_build_moc:
            self.dependencies.add(_MocSource(file, self))

        self.debug('source files to moc: %s', ', '.join([p.name for p in self.moc_sources]))


    async def __clean__(self):
        await super().__clean__()
        self.cache['moc_sources'] = list()


def wrap(modules: list[str] = None, ui_files: list[str] = None, resource_files: list[str] = None, build_moc=True,  major=6):
    if modules is None:
        modules = ['Widgets']
    if ui_files is None:
        ui_files = []
    if resource_files is None:
        resource_files = []
    def decorator(cls):
        from dan.core.include import context
        @context.current.wraps(cls)
        class QtWapped(_Wrapper, cls):
            __name__ = f'{cls.__name__}QtWrapped'
            qt_modules = modules
            qt_ui_files = ui_files
            qt_resource_files = resource_files
            qt_major = major
            qt_build_moc = build_moc
        return QtWapped
    return decorator

