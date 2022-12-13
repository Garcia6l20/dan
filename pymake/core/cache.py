import atexit
from functools import cached_property
import functools
from pathlib import Path
from collections.abc import Iterable

import yaml

class SubCache:
    pass

class Cache:
    __all: list['Cache'] = None

    def __init__(self, path: Path) -> None:
        self.__path = path
        if self.__path.exists():
            data = yaml.load(
                open(self.__path, 'r'), Loader=yaml.Loader)
            if isinstance(data, dict):
                self.__dict__.update(data)
        self.__init_hash = hash(self)
        if Cache.__all is None:
            Cache.__all = list()
            atexit.register(Cache.save_all)
        Cache.__all.append(self)

    @property
    def items(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_') and not isinstance(v, property)}

    @cached_property
    def modification_time(self) -> float:
        return self.__path.stat().st_mtime if self.__path.exists() else 0.0

    @staticmethod
    def __iterable_hash(l: Iterable):
        h = 0
        for v in l:
            h ^= hash(v)
        return h

    @staticmethod
    def __dict_hash(d: dict):
        h = 0
        for k, v in d.items():
            if isinstance(v, dict):
                vh = Cache.__dict_hash(v)
            if isinstance(v, Iterable):
                vh = Cache.__iterable_hash(v)
            else:
                vh = hash(v)
            h ^= hash(k) ^ vh
        return h

    def __hash__(self) -> int:
        return self.__dict_hash(self.items)

    @property
    def dirty(self):
        return self.__init_hash != hash(self)

    def remove(self):
        if self.__path:
            self.__path.unlink(missing_ok=True)

    def save(self):
        if self.__path and self.dirty:
            items = self.items
            if 'modification_time' in items:
                del items['modification_time']
            yaml.dump(items, open(self.__path, 'w'))

    def subcache(self, name):
        if hasattr(self, name):
            return getattr(self, name)
        else:
            sub = SubCache()
            setattr(self, name, sub)
            return sub

    @staticmethod
    def save_all():
        for c in Cache.__all:
            c.save()


def once_method(fn):    
    result_name = f'_{fn.__name__}_result'

    @functools.wraps(fn)
    def wrapper(self, *args, **kwds):
        if hasattr(self, result_name):
            return getattr(self, result_name)
        
        result = fn(self, *args, **kwds)
        setattr(self, result_name, result)
        return result

    return wrapper


