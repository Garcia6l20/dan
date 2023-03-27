from asyncio import *
import functools
import threading


class _CacheCtx:
    class Result:
        def __init__(self) -> None:
            self.event = Event()
            self.result = None

    def __init__(self) -> None:
        self.results: dict[int, self.Result] = dict()


def cached(fn):
    setattr(fn, '_aio_cache_ctx', _CacheCtx())

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        ctx: _CacheCtx = getattr(fn, '_aio_cache_ctx')
        key = hash((args, frozenset(kwargs)))
        if key not in ctx.results:
            # print(f'calling {fn} ({key})')
            result = _CacheCtx.Result()
            ctx.results[key] = result
            result.result = await fn(*args, **kwargs)
            result.event.set()
        else:
            await ctx.results[key].event.wait()

        return ctx.results[key].result

    return wrapper


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
