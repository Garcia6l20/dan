from pymake import self
from pymake.logging import debug
from pymake import include

self.name = 'pymake-examples'

say_yes = self.options.add('say_yes', False)
if say_yes.value:
    debug('Yes')

include('simple')
include('cxx')
