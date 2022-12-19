from pymake import requires
from pymake.cxx import Executable

Executable('test_spdlog',
           sources=['test_spdlog.cpp'],
           private_includes=['.'],
           dependencies=requires('spdlog')
           )
