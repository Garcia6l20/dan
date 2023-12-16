
import functools
import typing as t
from dan.core import asyncio
from dan.core.pm import re_match
from dan.core.settings import InstallMode, InstallSettings

from dan.core.version import VersionSpec
from dan.logging import Logging

def parse_package(name: str) -> tuple[str, str, str]:
    """Parse package name
    
    :returns: package, library, repository"""
    match re_match(name):
        # full specification <pkg>:<lib>@<repo>
        case r'(.+?):(.+?)@(.+)' as m:
            package = m[1]
            library = m[2]
            repository = m[3]
        # repo specification <lib>@<repo>
        case r'(.+?)@(.+)' as m:
            package = None
            library = m[1]
            repository = m[2]
        # package specification <pkg>:<lib>
        case r'(.+?):(.+)' as m:
            package = m[1]
            library = m[2]
            repository = None
        # no specification, automatic resolution in default repository
        case _:
            package = None
            library = name
            repository = None
    
    return package, library, repository


class RequiredPackage(Logging):
    
    @t.overload
    def __init__(self, specification_str: str): ...
    
    @t.overload
    def __init__(self, name: str, version_spec: VersionSpec): ...

    def __init__(self, *args):
        if len(args) == 2:
            name = args[0]
            self.version_spec = args[1]
        else:
            name, self.version_spec = VersionSpec.parse(args[0])
        self.target : 'Target' = None
        self.pn = name
        self.package, self.name, self.repository = parse_package(name)
        # fullfill Logging requirements
        setattr(self, 'fullname', str(self))
        setattr(self, '_logger', None)
        self.__skipped = list()

    def __getstate__(self) -> object:
        return {
            'pn': self.pn,
            'version_spec': self.version_spec,
        }
    
    def __setstate__(self, data):
        self.__init__(data['pn'], data['version_spec'])


    def is_compatible(self, t: 'Target'):
        if self.version_spec is not None:
            version_ok = self.version_spec.is_compatible(t.version)
        else:
            version_ok = True
        return version_ok
    
    @property
    def found(self):
        return self.target is not None
    
    @property
    def modification_time(self):
        return self.target.modification_time if self.target else 0.0

    def __skipped_method_call(self, name, *args, **kwargs):
        if name not in self.__skipped:
            self.debug('call to %s skipped (unresolved)', name)
            self.__skipped.append(name)

    def __getattr__(self, name):
        if not self.found:
            return functools.partial(self.__skipped_method_call, name)
        else:
            return getattr(self.target, name)
    
    def __str__(self) -> str:
        if self.version_spec:
            return f'RequiredPackage[{self.name} {self.version_spec}]'
        return f'RequiredPackage[{self.name}]'
    
    def __repr__(self) -> str:
        return f'{self} at {hex(id(self))}'
    

def parse_requirement(req: str) -> RequiredPackage:
    req = req.strip()
    name, spec = VersionSpec.parse(req)
    if spec:
        return RequiredPackage(name, spec)
    else:
        return RequiredPackage(req)

async def load_requirements(requirements: t.Iterable[RequiredPackage], makefile, name=None, logger = None, install = True):

    from dan.pkgconfig.package import find_package
    from dan.logging import _get_makefile_logger
    from dan.io import IoPackage

    if name is None:
        name = makefile.name

    if logger is None:
        logger = _get_makefile_logger()

    deps_install_path = makefile.root.pkgs_path
    deps_settings = InstallSettings(deps_install_path)

    pkgs_search_paths = [deps_install_path]
    if makefile.requirements:
        pkgs_search_paths.append(makefile.requirements.pkgs_path)

    resolved: list[RequiredPackage] = list()
    unresolved: list[RequiredPackage] = list()

    # async with progress.TaskGroup(f'loading {name} requirements', progress_options = { 'disable': not install }) as group:
    async with asyncio.TaskGroup(f'loading {name} requirements') as group:
        for req in requirements:
            if req.found:
                resolved.append(req)
                continue

            t = makefile.context.root.find(req.name)
            if t and not t.is_requirement and req.is_compatible(t):
                logger.debug('%s: already fullfilled by %s', req, t.fullname)
                req.target = t
                resolved.append(req)
                continue

            t = find_package(req.name, req.version_spec, search_paths=pkgs_search_paths, makefile=makefile)
            if t is not None and req.is_compatible(t):
                logger.debug('%s: using package %s', req, t.fullname)
                req.target = t
                resolved.append(req)
                continue
            
            if makefile.requirements:
                # install requirement from dan-requires.py
                t = makefile.requirements.find(req.name)
                if not t:
                    raise RuntimeError(f'Unresolved requirement {req}, it should have been defined in {makefile.requirements.__file__}')
                logger.debug('%s using requirements\' target %s', req, t.fullname)
            else:
                with makefile.context:
                    t, is_new = await IoPackage.instance(req.name, req.version_spec, package=req.package, repository=req.repository, makefile=makefile.root)
                if is_new:
                    logger.debug('%s: adding package %s', req, t.fullname)
                elif install:
                    logger.debug('%s: package already beeing installed at version %s', req, t.version)

            if install:
                group.create_task(t.install(deps_settings, InstallMode.dev))
            unresolved.append(req)

    if install:
        for req in unresolved:
            pkg = find_package(req.name, req.version_spec, search_paths=pkgs_search_paths, makefile=makefile)
            if pkg is None:
                raise RuntimeError(f'Unresolved requirement {req}')
            req.target = pkg
            resolved.append(req)

    return [req.target for req in resolved]
