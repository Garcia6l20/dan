from pymake import cli
from pymake.cxx import Executable

simple = Executable(sources=['test.cpp', 'main.cpp'], include_paths=['.'])

if __name__ == '__main__':
    cli()
