import inspect
from dan.core.pathlib import Path
import os

import typing as t

T = t.TypeVar("T")


class chdir:
    def __init__(self, path: Path, create=True, strict=False):
        self.path = path
        self.strict = strict
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        self.prev = None

    def __enter__(self):
        self.prev = Path.cwd()
        os.chdir(self.path)
        return None

    def __exit__(self, *args):
        try:
            os.chdir(self.prev)
        except OSError:
            if self.strict:
                raise


def unique(*seqs):
    seen = set()
    full = list()
    for seq in seqs:
        full.extend(seq)
    return [x for x in full if not (x in seen or seen.add(x))]


def chunks(lst, chunk_size):
    for ii in range(0, len(lst), chunk_size):
        yield lst[ii : ii + chunk_size]


class _ClassPropertyDescriptor(object):
    def __init__(self, fget, fset=None):
        self.fget = fget
        self.fset = fset

    def __get__(self, obj, klass=None):
        if klass is None:
            klass = type(obj)
        return self.fget.__get__(obj, klass)()

    def __set__(self, obj, value):
        if not self.fset:
            raise AttributeError("can't set attribute")
        type_ = type(obj)
        return self.fset.__get__(obj, type_)(value)

    def setter(self, func):
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.fset = func
        return self


def classproperty(func):
    if not isinstance(func, (classmethod, staticmethod)):
        args = inspect.getfullargspec(func).args
        match len(args):
            case 0:
                func = staticmethod(func)
            case 1:
                func = classmethod(func)
            case _:
                raise AttributeError(
                    "classproperty can only have 0 or 1 argument (the class object)"
                )

    return _ClassPropertyDescriptor(func)


class Environment(dict):
    def path_prepend(self, *items: str | Path, var_name="PATH"):
        paths: list[str] = self.get(var_name, "").split(os.pathsep)
        paths = [*[str(item) for item in items], *paths]
        self[var_name] = os.pathsep.join(unique(paths))

    def path_append(self, *items: str | Path, var_name="PATH"):
        paths: list[str] = self.get(var_name, "").split(os.pathsep)
        paths = [*paths, *[str(item) for item in items]]
        self[var_name] = os.pathsep.join(unique(paths))


class IndexList(list[T]):
    def __init__(self, iterable: t.Iterable[T], index_key="name"):
        self.__index_key = index_key
        super().__init__(iterable)

    def __getitem__(self, index) -> T | None:
        match index:
            case int() | slice():
                return super().__getitem__(index)
            case _:
                for item in super():
                    if getattr(item, self.__index_key, None) == index:
                        return item
