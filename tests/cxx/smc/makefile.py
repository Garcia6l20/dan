import asyncio
from pymake import cli
from pymake.cxx import Executable, Library
from pymake.smc import GitSources

gitfmt = GitSources('fmt', 'https://github.com/fmtlib/fmt.git', '8.1.1')
asyncio.run(gitfmt.build())

fmt_src = gitfmt.output / 'src'
fmt_inc = gitfmt.output / 'include'

fmt = Library(sources=[
    fmt_src / 'format.cc',
    fmt_src / 'os.cc'],
    public_includes=[fmt_inc],
    static=True,
    dependencies=[gitfmt])

test_fmt = Executable(sources=['main.cpp'],
                      private_includes=['.'],
                      dependencies=[fmt])

if __name__ == '__main__':
    cli()
