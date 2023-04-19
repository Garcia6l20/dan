from asyncio import *
import threading

from pymake.core.functools import BaseDecorator


class cached(BaseDecorator):

    def __init__(self, fn):
        self.__fn = fn
        self.__cache: dict[int, Future] = dict()

    async def __call__(self, *args, **kwds):
        key = hash((args, frozenset(kwds)))
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
        self.__cache = dict()


class _SyncWaitThread(threading.Thread):
    def __init__(self, coro):
        self.coro = coro
        self.result = None
        self.err = None
        super().__init__()

    def run(self):
        try:
            self.result = run(self.coro)
        except Exception as err:
            self.err = err


def sync_wait(coro):
    thread = _SyncWaitThread(coro)
    thread.start()
    thread.join()
    if thread.err:
        raise thread.err
    return thread.result
