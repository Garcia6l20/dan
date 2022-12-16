from pymake import self, include
from pymake.cxx import Executable

spdlog, fmt = include('spdlog')

Executable('test_spdlog',
           sources=['test_spdlog.cpp'],
           private_includes=['.'],
           dependencies=[spdlog, fmt])

self.install(spdlog)
