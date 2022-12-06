from pymake import cli
from pymake.cxx import Executable

simple = Executable(sources=['test.cpp', 'main.cpp'], private_includes=['.'])

if __name__ == '__main__':
    cli()
