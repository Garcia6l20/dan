from asyncio import *
from async_property import *

import threading
import concurrent.futures
import multiprocessing
import typing as t
import inspect
import threading

from dan.core.functools import BaseDecorator


async def may_await(obj):
    """Awaits given object if it is an awaitable

    If obj is an awaitable it's await-result is returned.
    If obj is not an awaitable it is returned directly.
    """
    if inspect.isawaitable(obj):
        return await obj
    else:
        return obj


class Cached(BaseDecorator):
    def __init__(self, fn, unique=False):
        self.__fn = fn
        self.__unique = unique
        self.__is_method = fn.__call__.__class__.__name__ == "method-wrapper"
        if not self.__is_method and self.__unique:
            self.__cache = None
        else:
            self.__cache: dict[int, Future] = dict()

    async def __call__(self, *args, **kwds):
        if not self.__is_method and self.__unique:
            if self.__cache is None:
                self.__cache = Future()
                try:
                    self.__cache.set_result(await self.__fn(*args, **kwds))
                except Exception as ex:
                    self.__cache.set_exception(ex)
            elif not self.__cache.done():
                await self.__cache
            return self.__cache.result()
        else:
            args = tuple(filter(lambda a: a is not None, args))
            key = id(args[0]) if self.__unique else hash((args, frozenset(kwds)))
            if key not in self.__cache:
                self.__cache[key] = Future()
                try:
                    self.__cache[key].set_result(await self.__fn(*args, **kwds))
                except Exception as ex:
                    self.__cache[key].set_exception(ex)
            elif not self.__cache[key].done():
                await self.__cache[key]

            return self.__cache[key].result()

    def clear_all(self):
        if self.__unique:
            self.__cache = dict()
        else:
            self.__cache = None


def cached(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return Cached(args[0])
    else:

        def wrapper(fn):
            return Cached(fn, *args, **kwargs)

        return wrapper


class _SyncWaitThread(threading.Thread):
    def __init__(self, coro):
        self.coro = coro
        self.result = None
        self.err = None
        super().__init__()

    def run(self):
        try:
            loop = new_event_loop()
            self.result = loop.run_until_complete(self.coro)
            tasks = all_tasks(loop)
            if len(tasks):
                for t in tasks:
                    t.cancel()
                loop.run_until_complete(wait(tasks))
        except Exception as err:
            self.err = err


def sync_wait(coro):
    thread = _SyncWaitThread(coro)
    thread.start()
    thread.join()
    if thread.err:
        raise thread.err
    return thread.result


_async_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=multiprocessing.cpu_count(),
)


async def async_wait(fn, *args, **kwargs):
    loop = get_running_loop()

    def wrapper():
        return fn(*args, **kwargs)

    return await loop.run_in_executor(_async_pool, wrapper)


async def return_exceptions(coro, exceptions=(Exception,)):
    try:
        return await coro
    except exceptions as err:
        return err


from asyncio import TaskGroup as OrigTaskGroup


class TaskGroup(OrigTaskGroup):
    def __init__(self, name=None, never_abort=False, return_exceptions=False) -> None:
        super().__init__()
        self.name = name
        self.__tasks: list[Task] = list()
        self._never_abort = never_abort
        self._return_exceptions = return_exceptions

    def _abort(self):
        if not self._never_abort:
            super()._abort()

    def create_task(self, coro, *, name=None, context=None) -> Task:
        if self._return_exceptions:
            coro = return_exceptions(coro)
        t = super().create_task(coro, name=name, context=context)
        self.__tasks.append(t)
        return t

    def results(self):
        return (t.result() for t in self.__tasks)


class async_lock:
    def __init__(self, lock):
        self.lock = lock

    async def __aenter__(self):
        loop = get_event_loop()
        await loop.run_in_executor(_async_pool, self.lock.acquire)

    async def __aexit__(self, *args):
        self.lock.release()


class ThreadLock:
    def __init__(self) -> None:
        self._lk = threading.Lock()

    def __enter__(self):
        self._lk.acquire()

    def __exit__(self, *exc):
        self._lk.release()

    async def __aenter__(self):
        loop = get_event_loop()
        await loop.run_in_executor(_async_pool, self._lk.acquire)

    async def __aexit__(self, *exc):
        self._lk.release()


spawn = create_task
