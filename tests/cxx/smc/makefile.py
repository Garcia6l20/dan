from pymake import self, include
from pymake.cxx import Executable

spdlog, fmt = include('spdlog')

test_spdlog = Executable(sources=['main.cpp'],
                      private_includes=['.'],
                      dependencies=[spdlog, fmt])

self.export(spdlog, fmt)
