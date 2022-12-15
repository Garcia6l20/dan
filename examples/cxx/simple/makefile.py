from pymake.cxx import Executable

simple = Executable('simple', sources=['test.cpp', 'main.cpp'], private_includes=['.'])
greater = simple.options.add('greater', 'hello pymake')
simple.compile_definitions.add(f'SIMPLE_GREATER="\\"{greater.value}\\""')
