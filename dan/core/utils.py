import inspect
from dan.core.pathlib import Path
import os


class chdir:
    def __init__(self, path: Path, create=True):
        self.path = path
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        self.prev = None

    def __enter__(self):
        self.prev = Path.cwd()
        os.chdir(self.path)
        return None

    def __exit__(self, *args):
        os.chdir(self.prev)


def unique(*seqs):
    seen = set()
    full = list()
    for seq in seqs:
        full.extend(seq)
    return [x for x in full if not (x in seen or seen.add(x))]


def chunks(lst, chunk_size):
    for ii in range(0, len(lst), chunk_size):
        yield lst[ii:ii + chunk_size]


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
                raise AttributeError("classproperty can only have 0 or 1 argument (the class object)")

    return _ClassPropertyDescriptor(func)
