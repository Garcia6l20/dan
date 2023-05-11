from pymake import self
from pymake.logging import info
from pymake import include

self.name = 'pymake-examples'

say_yes = self.options.add('say_yes', False, help='A basic option example, set it to true to log "Yes" when makefile is invoked.')
if say_yes.value:
    info('Yes')

include('simple')
include('cxx')
