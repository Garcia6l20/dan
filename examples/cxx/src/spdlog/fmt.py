from dan import self
from dan.cxx import Library
from dan.src.github import GitHubReleaseSources

version = '9.1.0'
description = 'A modern formatting library'

class FmtSources(GitHubReleaseSources):
    user = 'fmtlib'
    project = 'fmt'

class Fmt(Library):
    name = 'fmt'
    preload_dependencies = FmtSources,
    
    async def __initialize__(self):        
        src = self.get_dependency(FmtSources).output
        self.includes.add(src / 'include', public=True)
        self.sources = [
            src / 'src/format.cc',
            src / 'src/os.cc',
        ]
        await super().__initialize__()
