from pymake import cli, include
from pymake.cxx import Executable

fmt = include('fmt')

test_fmt = Executable(sources=['main.cpp'],
                      private_includes=['.'],
                      dependencies=[fmt])

exports = fmt

if __name__ == '__main__':
    cli()
