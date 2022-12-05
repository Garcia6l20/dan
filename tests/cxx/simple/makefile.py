from pymake.cxx import Executable

simple = Executable(sources=['test.cpp', 'main.cpp'], include_paths=['.'])
