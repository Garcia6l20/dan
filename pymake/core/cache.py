import functools
import aiofiles
import yaml
import typing as t

from pymake.core.pathlib import Path
from pymake.core import asyncio

T = t.TypeVar('T', bound=dict)

class Cache(t.Generic[T]):
    dataclass: T = dict
    __caches: dict[str, 'Cache'] = dict()

    def __init_subclass__(cls) -> None:
        cls.dataclass = t.get_args(cls.__orig_bases__[0])[0]
        return super().__init_subclass__()

    def __init__(self, path: Path|str, *args, cache_name:str = None, **kwargs):
        self.__path = Path(path)     
        self.__name = cache_name or path.stem   
        assert not self.name in self.__caches, 'a cache type should be unique'
        if self.path.exists():
            with open(self.path, 'r') as f:
                self.__data = yaml.load(f, Loader=yaml.Loader)
                if not isinstance(self.__data, self.dataclass):
                    self.__data = self.dataclass(**self.__data)
                self.__modification_date = self.path.modification_time
        else:
            self.__data = self.dataclass(*args, **kwargs)
            self.__modification_date = 0.0
        self.__caches[self.name] = self
    
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
        return True
    
    async def save(self):
        if self.path and self.dirty:
            data = yaml.dump(self.data)
            if data:
                self.path.parent.mkdir(exist_ok=True, parents=True)
                async with aiofiles.open(self.path, 'w') as f:
                    await f.write(data)

    @classmethod
    async def save_all(cls):
        async with asyncio.TaskGroup('saving caches') as group:
            for c in cls.__caches.values():
                group.create_task(c.save())

    @classmethod
    def get(cls, name) -> 'Cache':
        if name in cls.__caches:
            return cls.__caches[name]

    def ignore(self):
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


