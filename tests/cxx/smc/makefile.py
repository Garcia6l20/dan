from pymake import self, include
from pymake.cxx import Executable

spdlog, fmt = include('spdlog')
catch2, = include('catch2')

Executable('test_spdlog',
           sources=['test_spdlog.cpp'],
           private_includes=['.'],
           dependencies=[spdlog, fmt])

Executable('test_catch2',
           sources=['test_catch2.cpp'],
           private_includes=['.'],
           dependencies=[catch2])

self.export(spdlog, fmt)
