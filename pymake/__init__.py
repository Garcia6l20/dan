import sys
import pymake.core.include
from pymake.core.include import include, requires, export
from pymake.core.generator import generator


self : pymake.core.include.MakeFile

class __LazySelf(sys.__class__):
    @property
    def self(__):
        return pymake.core.include.context.current

sys.modules[__name__].__class__ = __LazySelf

