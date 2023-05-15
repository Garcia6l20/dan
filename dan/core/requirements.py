
import functools
import re
import typing as t
from dan.core import asyncio
from dan.core.pm import re_match
from dan.core.settings import InstallMode, InstallSettings

from dan.core.version import Version, VersionSpec
from dan.logging import Logging


class RequiredPackage(Logging):
    def __init__(self, name: str, version_spec: VersionSpec = None):
        self.version_spec = version_spec
        super().__init__(name)
        self.target : 'Target' = None

        match re_match(name):
            case r'(.+?)@(.+)' as m:
                self.name = m[1]
                self.provider = m[2]
            case _:
                self.name = name
                self.provider = None

    def is_compatible(self, t: 'Target'):
        if self.version_spec is not None:
            version_ok = self.version_spec.is_compatible(t.version)
        else:
            version_ok = True
        return t.name == self.name and version_ok
    
    @property
    def found(self):
        return self.target is not None
    
    @property
    def modification_time(self):
        return self.target.modification_time if self.target else 0.0

    def __skipped_method_call(self, name, *args, **kwargs):
        self.debug('call to %s skipped (unresolved)', name)

    def __getattr__(self, name):
        if not self.found:
            return functools.partial(self.__skipped_method_call, name)
        else:
            return getattr(self.target, name)
    
    def __str__(self) -> str:
        if self.version_spec:
            return f'RequiredPackage[{self.name} {self.version_spec}]'
        return f'RequiredPackage[{self.name}]'
    

def parse_requirement(req: str) -> RequiredPackage:
    req = req.strip()
    name, spec = VersionSpec.parse(req)
    if spec:
        return RequiredPackage(name, spec)
    else:
        return RequiredPackage(req)

async def load_requirements(requirements: t.Iterable[RequiredPackage], makefile, logger = None, install = True):

    from dan.pkgconfig.package import find_package
    from dan.logging import _get_makefile_logger
    from dan.core.include import context
    from dan.io import Package

    if logger is None:
        logger = _get_makefile_logger()

    deps_install_path = makefile.pkgs_path
    deps_settings = InstallSettings(deps_install_path)

    pkgs_search_paths = [deps_install_path]
    if makefile.requirements:
        pkgs_search_paths.append(makefile.requirements.pkgs_path)

    result = list()
    unresolved = list()

    async with asyncio.TaskGroup('requirement loading') as group:
        for req in requirements:
            if req.found:
                result.append(req.target)
                continue

            t = context.root.find(req.name)
            if t and not t.is_requirement and req.is_compatible(t):
                req.target = t
                result.append(req.target)
                continue

            t = find_package(req.name, req.version_spec, search_paths=pkgs_search_paths, makefile=makefile)
            if t is not None and req.is_compatible(t):
                req.target = t
                result.append(t)
            elif install:
                if makefile.requirements:
                    # install requirement from dan-requires.py
                    t = makefile.requirements.find(req.name)
                    if not t:
                        raise RuntimeError(f'Unresolved requirement {req}, it should have been defined in {makefile.requirements.__file__}')
                else:
                    t = Package(req.name, req.version_spec, repository=req.provider, makefile=makefile)
                logger.debug('installing requirement: %s %s', req.name, req.version_spec)
                unresolved.append(req)                
                group.create_task(t.install(deps_settings, InstallMode.dev))



    if install:
        for req in unresolved:
            pkg = find_package(req.name, req.version_spec, search_paths=pkgs_search_paths, makefile=makefile)
            if pkg is None:
                raise RuntimeError(f'Unresolved requirement {req}')
            req.target = pkg
            result.append(pkg)

    return result
