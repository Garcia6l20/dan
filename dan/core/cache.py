import dataclasses
import functools
import json
import pickle
import aiofiles
import typing as t


from dan.core.pathlib import Path
from dan.core import asyncio

T = t.TypeVar('T', bound=dict)

class Cache(t.Generic[T]):
    dataclass: T = dict
    indent = None
    __caches: dict[str, 'Cache'] = dict()

    def __init_subclass__(cls) -> None:
        cls.dataclass = t.get_args(cls.__orig_bases__[0])[0]
        return super().__init_subclass__()

    def __init__(self, path: Path|str, *args, cache_name:str = None, binary=False, **kwargs):
        self.__path = Path(path)     
        self.__name = cache_name or path.stem   
        self.__serializer = json if not binary else pickle
        if self.name in self.__caches:
            other = Cache.get(self.name)
            if other.path == self.path:
                raise RuntimeError(f'Cache {self.name} already created, use Cache.instance')
            else:
                raise RuntimeError(f'Cache {self.name} is not unique, use cache_name to distinguish {other.path} from {self.path}')

        assert not self.name in self.__caches, 'a cache should be unique'
        self.__caches[self.name] = self

        if self.path.exists():
            with open(self.path, 'rb') as f:
                if dataclasses.is_dataclass(self.dataclass):
                    self.__data = self.dataclass.from_json(f.read())
                else:
                    self.__data = self.__serializer.load(f)
                if not isinstance(self.__data, self.dataclass):
                    self.__data = self.dataclass(**self.__data)
                self.__modification_date = self.path.modification_time
        else:
            self.__data = self.dataclass(*args, **kwargs)
            self.__modification_date = 0.0
        
        self.__initial_state = self._dump()
        self.__dirty = False
    
    @classmethod
    def instance(cls, path: Path|str, *args, cache_name:str = None, **kwargs):
        cache_name = cache_name or path.stem
        if cache_name in cls.__caches:
            return cls.__caches[cache_name]
        return cls(path, *args, cache_name=cache_name, **kwargs)

    @classmethod
    def clear_all(cls):
        del cls.__caches
        cls.__caches = dict()
    
    def _dump(self):        
        if self.__serializer is pickle:
            return self.__serializer.dumps(self.data)
        else:
            if self.dataclass == dict:
                return self.__serializer.dumps(self.data).encode()
            else:
                return self.data.to_json(indent=self.indent).encode()

    
    @property
    def path(self):
        return self.__path
    
    @property
    def name(self):
        return self.__name
    
    @property
    def data(self) -> T|dict:
        return self.__data
    
    @property
    def dirty(self):
        if not self.__dirty:
            self.__state = self._dump()
            self.__dirty = self.__initial_state != self.__state
        return self.__dirty
    
    async def save(self, force=False):
        if self.path and (self.dirty or force):
            if self.__state:
                self.path.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(self.path, 'wb') as f:
                    await f.write(self.__state)
                self.__dirty = False

    @classmethod
    async def save_all(cls):
        async with asyncio.TaskGroup('saving caches') as group:
            for c in cls.__caches.values():
                if c.dirty:
                    group.create_task(c.save())

    @classmethod
    def get(cls, name) -> 'Cache':
        if name in cls.__caches:
            return cls.__caches[name]

    def ignore(self):
        if self.name in self.__caches:
            del self.__caches[self.name]


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

class _CachedProperty:
    def __init__(self, getter: t.Callable[[], t.Any], cache_name=None):
        self.__getter = getter
        self.__name = getter.__name__
        self.__cache_name = 'cache' if cache_name is None else cache_name

    def __get__(self, instance, owner: type | None = None):
        cache = getattr(instance, self.__cache_name)
        if isinstance(cache, Cache):
            cache = cache.data
        value = cache.get(self.__name)
        if value is None:
            value = self.__getter(instance)
            if value is not None:
                cache[self.__name] = value
        return value

    def __set__(self, instance, value):
        cache = getattr(instance, self.__cache_name)
        if isinstance(cache, Cache):
            cache = cache.data
        cache[self.__name] = value

    def __delete__(self, instance):
        cache = getattr(instance, self.__cache_name)
        del cache[self.__name]


def cached_property(cache_name=None):
    def wrapper(fn):
        return _CachedProperty(fn, cache_name=cache_name)
    return wrapper
