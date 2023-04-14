from pymake import self
from pymake.cxx import Library
from pymake.smc import GitSources

version = '9.1.0'
description = 'A modern formatting library'

gitfmt = GitSources('fmt', 'https://github.com/fmtlib/fmt.git', version)

fmt_src = gitfmt.output / 'src'
fmt_inc = gitfmt.output / 'include'

fmt = Library('fmt',
              description=description,
              version=version,
              sources=[
                  fmt_src / 'format.cc',
                  fmt_src / 'os.cc',
              ],
              includes=[fmt_inc],
              preload_dependencies=[gitfmt],
              all=False)

self.install(fmt)
