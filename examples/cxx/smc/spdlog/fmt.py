from pymake import self
from pymake.cxx import Library
from pymake.smc import GitSources

version = '9.1.0'
description = 'A modern formatting library'

class FmtSources(GitSources):
    name = 'fmt-source'
    url = 'https://github.com/fmtlib/fmt.git'
    refspec = version

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
