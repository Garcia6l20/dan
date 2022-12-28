from pymake import self, requires
from pymake.cxx import Executable

example = Executable('pymake-test-catch2',
                     sources=['test_catch2.cpp'],
                     private_includes=['.'],
                     dependencies=requires('catch2'))


def discover_tests(exe: Executable):
    from pymake import self as makefile
    import yaml
    output = exe.build_path / f'{exe.name}-tests.yaml'
    filepath = exe.source_path / exe.sources[0]
    if not output.exists() or output.older_than(filepath):
        import re
        test_macros = [
            'TEST_CASE',
            'SCENARIO'
        ]
        expr = re.compile(
            fr"({'|'.join(test_macros)})\(\s?\"([\w\s]+)\"[\s,]{{0,}}(?:\"(.+)\")?\)")  # (,.+)?\)"
        tests = dict()
        with open(filepath, 'r') as f:
            content = f.read()
            prev_pos = 0
            lineno = 1
            for m in expr.finditer(content):
                title = m.group(2)
                pos = m.span()[0]
                lineno = content.count('\n', prev_pos, pos) + lineno
                prev_pos = pos
                tests[title] = {
                    'filepath': str(filepath),
                    'lineno': lineno,
                }
                tags = m.group(3)
                if tags:
                    tests[title]['tags'] = tags

        with open(output, 'w') as f:
            f.write(yaml.dump(tests))

    with open(output, 'r') as f:
        tests: dict = yaml.load(f.read(), yaml.Loader)
        for title, data in tests.items():
            makefile.add_test(exe, name=title, args=[
                              title], file=data['filepath'], lineno=data['lineno'])


discover_tests(example)

self.install(example)
