from pymake import cli, include
from pymake.cxx import Executable

spdlog, fmt = include('spdlog')

test_spdlog = Executable(sources=['main.cpp'],
                      private_includes=['.'],
                      dependencies=[spdlog, fmt])

exports = spdlog, fmt

if __name__ == '__main__':
    cli()
