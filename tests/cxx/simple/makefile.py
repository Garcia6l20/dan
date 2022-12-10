from pymake.cxx import Executable

simple = Executable(sources=['test.cpp', 'main.cpp'], private_includes=['.'])
