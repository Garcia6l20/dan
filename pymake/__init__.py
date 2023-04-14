import sys
import pymake.core.include
from pymake.core.include import include, requires, load
from pymake.core.generator import generator
from pymake.pkgconfig.package import find_package


self : pymake.core.include.MakeFile

class __LazySelf(sys.__class__):
    @property
    def self(__):
        return pymake.core.include.context.current

sys.modules[__name__].__class__ = __LazySelf
