from asyncio import *
import functools


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
