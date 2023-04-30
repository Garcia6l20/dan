import os
from pymake import self, requires
from pymake.cxx import Library
from pymake.smc import GitSources

requires('fmt')

version = '1.11.0'
description = 'Fast C++ logging library'


class SpdLogSources(GitSources):
    name = 'spdlog-source'
    url = 'https://github.com/gabime/spdlog.git'
    refspec = f'v{version}'


class Fmt(Library):
    name = 'spdlog'
    preload_dependencies = SpdLogSources,
    dependencies = 'fmt',
    public_compile_definitions = 'SPDLOG_COMPILED_LIB', 'SPDLOG_FMT_EXTERNAL'
    header_match = r'^(?:(?!bundled).)*\.(h.?)$'
    
    async def __initialize__(self):
        spdlog_root = self.get_dependency(SpdLogSources).output
        self.includes.add(spdlog_root  / 'include', public=True)
        spdlog_src = spdlog_root / 'src'
        self.sources = [
            spdlog_src / 'async.cpp',
            spdlog_src / 'cfg.cpp',
            spdlog_src / 'color_sinks.cpp',
            spdlog_src / 'file_sinks.cpp',
            spdlog_src / 'stdout_sinks.cpp',
            spdlog_src / 'spdlog.cpp',
        ]
        
        if self.toolchain.type != 'msvc':
            self.link_libraries.add('pthread', public=True)

        await super().__initialize__()

