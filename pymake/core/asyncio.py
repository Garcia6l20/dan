from asyncio import *
import functools
import inspect
import os

import aiofiles


class OnceLock:
    def __init__(self) -> None:
        self.__done = False
        self.__lock = Lock()

    @property
    def done(self):
        return self.__done

    @property
    def locked(self):
        return self.__lock.locked()

    async def __aenter__(self):
        await self.__lock.acquire()
        return self.__done

    async def __aexit__(self, exc_type, exc, tb):
        self.__done = True
        self.__lock.release()


def once_method(fn):
    lock_name = f'_{fn.__name__}_lock'
    result_name = f'_{fn.__name__}_result'

    async def inner(self, done, *args, **kwds):
        if done:
            return getattr(self, result_name)
        result = fn(self, *args, **kwds)
        if inspect.iscoroutine(result):
            result = await result
        setattr(self, result_name, result)
        return result

    @functools.wraps(fn)
    async def wrapper(self, *args, **kwds):
        if not hasattr(self, lock_name):
            lock = OnceLock()
            setattr(self, lock_name, lock)
        else:
            lock = getattr(self, lock_name)
        # name = self.name if hasattr(self, "name") else self.__class__.__name__
        # fn_name = fn.__name__
        # if not lock.done:
        #     print(f'{name}.{fn_name} {"not " if not lock.locked else ""}locked')
        # else:
        #     print(f'{name}.{fn_name} done')
        recursive_once = kwds.pop('recursive_once', False)
        if recursive_once:
            return await inner(self, lock.done, *args, **kwds)
        async with lock as done:
            return await inner(self, done, *args, **kwds)

    return wrapper
