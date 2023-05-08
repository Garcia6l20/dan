
import functools
import re
import typing as t
from pymake.core import asyncio
from pymake.core.settings import InstallMode, InstallSettings

from pymake.core.version import Version, VersionSpec
from pymake.logging import Logging


class RequiredPackage(Logging):
    def __init__(self, name: str, version_spec: VersionSpec = None):
        self.name = name
        self.version_spec = version_spec
        super().__init__(name)
        self.target : 'Target' = None

    def is_compatible(self, t: 'Target'):
        if self.version_spec is not None:
            version_ok = self.version_spec.is_compatible(t.version)
        else:
            version_ok = True
        return t.name == self.name and version_ok
    
    @property
    def found(self):
        return self.target is not None
    
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
    m = re.match(r'(.+?)\s+([><]=?|=)\s+([\d\.]+)', req)
    if m:
        name = m[1]
        op = m[2]
        version = Version(m[3])
        return RequiredPackage(name, VersionSpec(version, op))
    else:
        return RequiredPackage(req)

async def load_requirements(requirements: t.Iterable[RequiredPackage], makefile, logger = None, install = True):

    from pymake.pkgconfig.package import find_package
    from pymake.logging import _get_makefile_logger
    from pymake.core.include import context

    if logger is None:
        logger = _get_makefile_logger()

    deps_install_path = makefile.pkgs_path
    deps_settings = InstallSettings(deps_install_path)

    result = list()
    unresolved = list()

    async with asyncio.TaskGroup('requirement loading') as group:
        for req in requirements:
            if req.found:
                result.append(req.target)
                continue

            t = context.root.find(req.name)
            if t and req.is_compatible(t):
                req.target = t
                continue

            t = find_package(req.name, req.version_spec, search_paths=[deps_install_path], makefile=makefile)
            if t is not None and req.is_compatible(t):
                req.target = t
                result.append(t)
            elif install:
                t = makefile.requirements.find(req.name)
                if not t:
                    raise RuntimeError(f'Unresolved requirement {req}')
                logger.debug('installing requirement: %s %s', req.name, req.version_spec)
                unresolved.append(req)                
                group.create_task(t.install(deps_settings, InstallMode.dev))

    if install:
        for req in unresolved:
            pkg = find_package(req.name, req.version_spec, search_paths=[deps_install_path], makefile=makefile)
            if pkg is None:
                raise RuntimeError(f'Unresolved requirement {req}')
            req.target = pkg
            result.append(pkg)

    return result
