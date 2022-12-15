from pymake import self
from pymake.cxx import Executable

simple = Executable('pymake-simple', sources=['test.cpp', 'main.cpp'], private_includes=['.'])
greater = simple.options.add('greater', 'hello pymake')
simple.compile_definitions.add(f'SIMPLE_GREATER="\\"{greater.value}\\""')

self.install(simple)
