import asyncio
import atexit
from functools import cached_property
import functools
import weakref
from pymake.core.pathlib import Path
from collections.abc import Iterable
import aiofiles

import yaml



class SubCache(object):
    def __init__(self, parent: 'SubCache', name:str) -> None:
        self.__parent = weakref.ref(parent)
        self.__name = name

    @property
    def modification_time(self):
        return self.__parent().modification_time

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
            elif isinstance(v, Iterable):
                vh = Cache.__iterable_hash(v)
            elif isinstance(v, SubCache):
                vh = Cache.__dict_hash(v.__getstate__())
            else:
                vh = hash(v)
            h ^= hash(k) ^ vh
        return h

    def __hash__(self) -> int:
        return self.__dict_hash(self.__getstate__())


    def __getstate__(self):
        state = self.__dict__.copy()
        for k in self.__dict__.keys():
            if k.startswith('_'):
                del state[k]
        return state

    def get(self, name : str, default = None):
        return getattr(self, name) if hasattr(self, name) else default


class Cache(SubCache):

    def __init__(self, path: Path) -> None:
        self.__path = path
        if self.__path.exists():
            with open(self.__path, 'r') as f:
                data = yaml.load(f, Loader=yaml.Loader)
                if isinstance(data, dict):
                    self.__dict__.update(data)
                self.__modification_date = self.__path.stat().st_mtime
        else:
            self.__modification_date = 0.0
        self.__init_hash = hash(self)
        from pymake.core.include import context
        caches = context.get('_caches', list())
        caches.append(self)


    @property
    def modification_time(self) -> float:
        return self.__modification_date


    @property
    def dirty(self):
        return self.__init_hash != hash(self)

    def remove(self):
        if self.__path:
            self.__path.unlink(missing_ok=True)

    def subcache(self, name):
        if hasattr(self, name):
            return getattr(self, name)
        else:
            sub = SubCache(self, name)
            setattr(self, name, sub)
            return sub

    async def save(self):
        if self.__path and self.dirty:
            data = yaml.dump(self.__getstate__())
            if data:
                self.__path.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(self.__path, 'w') as f:
                    await f.write(data)

    @staticmethod
    async def save_all():
        from pymake.core.include import context
        caches = context.get('_caches')
        if caches:
            saves = list()
            for c in context._caches:
                saves.append(c.save())
            await asyncio.gather(*saves)


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


