from pymake import self, include
from pymake.cxx import Executable

spdlog, fmt = include('spdlog')

Executable('test_spdlog',
           sources=['main.cpp'],
           private_includes=['.'],
           dependencies=[spdlog, fmt])

self.export(spdlog, fmt)
