from pymake import include
import platform

include(
    'spdlog',
    'catch2',
)

if platform.system() == 'Linux':
    include('liburing')

