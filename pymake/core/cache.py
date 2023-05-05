import asyncio
import atexit
from functools import cached_property
import functools
import weakref
from pymake.core.pathlib import Path
from collections.abc import Iterable
import aiofiles

import yaml
import typing as t



T = t.TypeVar('T', bound=dict)

class Cache(t.Generic[T]):
    dataclass: T = dict
    __caches: dict[str, 'Cache'] = dict()

    def __init_subclass__(cls) -> None:
        cls.dataclass = t.get_args(cls.__orig_bases__[0])[0]
        return super().__init_subclass__()

    def __init__(self, path : Path|str, *args, **kwargs):
        self.__path = Path(path)        
        assert not self.__path in self.__caches, 'a cache type should be unique'
        if self.path.exists():
            with open(self.path, 'r') as f:
                self.__data = self.dataclass(**yaml.load(f, Loader=yaml.Loader))
                self.__modification_date = self.path.modification_time
        else:
            self.__data = self.dataclass(*args, **kwargs)
            self.__modification_date = 0.0
        self.__caches[self.__path] = self
    
    @property
    def path(self):
        return self.__path
    
    @property
    def name(self):
        return self.__path.stem
    
    @property
    def data(self) -> T|dict:
        return self.__data
    
    @property
    def dirty(self):
        return True
    
    async def save(self):
        if self.path and self.dirty:
            data = yaml.dump(self.data.__getstate__()) if self.dataclass != dict else yaml.dump(self.data)
            if data:
                self.path.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(self.path, 'w') as f:
                    await f.write(data)

    @classmethod
    async def save_all(cls):
        async with asyncio.TaskGroup() as group:
            for c in cls.__caches.values():
                group.create_task(c.save())

    def ignore(self):
        del self.__caches[self.__path]


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


