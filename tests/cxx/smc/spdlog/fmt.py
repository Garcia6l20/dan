from pymake import self
from pymake.cxx import Library
from pymake.smc import GitSources

gitfmt = GitSources('fmt', 'https://github.com/fmtlib/fmt.git', '9.1.0')

fmt_src = gitfmt.output / 'src'
fmt_inc = gitfmt.output / 'include'

fmt = Library('fmt',
              sources=[
                  fmt_src / 'format.cc',
                  fmt_src / 'os.cc',
              ],
              includes=[fmt_inc],
              preload_dependencies=[gitfmt],
              all=False)

self.export(fmt)
