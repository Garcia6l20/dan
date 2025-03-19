import typing as t
import functools

T_ = t.TypeVar("T_")


class Registry(t.Generic[T_]):

    _registry_classes: set[T_] = None
    _registry_final = False

    def __init_subclass__(cls: T_, internal=False, registry=False, final=False):
        if registry:
            cls._registry_classes = set()
        elif not internal and not cls._registry_final:
            cls.register(cls)
        if final:
            cls._registry_final = True

    @classmethod
    def register(cls: T_, other: T_):
        cls._registry_classes.add(other)

    @classmethod
    def registered_classes(cls, fltr: type | t.Callable = None):
        if fltr is None:
            return cls._registry_classes
        elif isinstance(fltr, type):

            def _fltr(subclass, c):
                return c != subclass and issubclass(c, subclass)

            fltr = functools.partial(_fltr, fltr)
        return filter(
            fltr,
            cls._registry_classes,
        )


class MakefileRegister:

    _highest_internal_class = None
    makefile = None

    def __init_subclass__(cls, *args, internal=False, **kwargs):
        if not internal:
            from dan.core.include import context

            cls.makefile = context.current
            cls.makefile.register(cls)
        else:
            cls._highest_internal_class = cls

    @classmethod
    def get_highest_internal_class(cls):
        return cls._highest_internal_class

    @classmethod
    def get_static_makefile(cls):
        return cls.makefile

    @property
    def context(self):
        return self.makefile.context
