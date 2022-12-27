from pymake import self, requires
from pymake.cxx import Executable

example = Executable('pymake-test-catch2',
                     sources=['test_catch2.cpp'],
                     private_includes=['.'],
                     dependencies=requires('catch2'))


def discover_tests(exe : Executable):
    import re
    test_macros = [
        'TEST_CASE',
        'SCENARIO'
    ]
    expr = fr"({'|'.join(test_macros)})\(\s?\"([\w\s]+)\"" #(,.+)?\)"
    tests = list()
    filepath = exe.source_path / exe.sources[0]
    with open(filepath, 'r') as f:
        for num, line in enumerate(f.readlines()):
            m = re.search(expr, line)
            if m is not None:
                title = m.group(2)
                #tags = m.group(3)
                tests.append((title, [title], filepath, num))
    for title, args, filepath, lineno in tests:
        self.add_test(exe, name=title, args=list(args), file=filepath, lineno=lineno)

discover_tests(example)
# self.add_test(example)
self.install(example)
