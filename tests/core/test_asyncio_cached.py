import unittest

from pymake.core import asyncio


@asyncio.cached
async def dtwice(x, delay=0.1):
    dtwice.call_count += 1
    return x * 2
setattr(dtwice, 'call_count', 0)


class CachedMember:
    def __init__(self) -> None:
        self.call_count = 0

    @asyncio.cached
    async def simple(self):
        assert isinstance(self, CachedMember)
        return 42

    @asyncio.cached
    async def twice(self, x):
        self.call_count += 1
        return x * 2


class AsyncioCachedTest(unittest.IsolatedAsyncioTestCase):

    async def test_cached_free_func(self):
        self.assertEqual(dtwice.call_count, 0)
        results = await asyncio.gather(
            dtwice(2),
            dtwice(2),
            dtwice(2),
            dtwice(4),
        )
        self.assertEqual(results[0], 4)
        self.assertEqual(results[1], 4)
        self.assertEqual(results[2], 4)
        self.assertEqual(results[3], 8)
        excepted_call_count = 2
        self.assertEqual(dtwice.call_count, excepted_call_count)

        # clear test (single)
        dtwice.clear(2)
        await asyncio.gather(
            dtwice(2),
            dtwice(4),
        )
        excepted_call_count += 1  # only dtwice(2) should have been called
        self.assertEqual(dtwice.call_count, excepted_call_count)

        # clear test (all)
        dtwice.clear_all()
        await asyncio.gather(
            dtwice(2),
            dtwice(4),
        )
        excepted_call_count += 2  # both should have been called
        self.assertEqual(dtwice.call_count, excepted_call_count)

    async def test_cached_member(self):
        o = CachedMember()
        await o.simple()

        excepted_call_count = 0
        self.assertEqual(o.call_count, excepted_call_count)

        await o.twice(1)
        await o.twice(1)
        excepted_call_count += 1
        self.assertEqual(o.call_count, excepted_call_count)

        o.twice.clear(1)
        await o.twice(1)
        excepted_call_count += 1
        self.assertEqual(o.call_count, excepted_call_count)

        results = await asyncio.gather(
            o.twice(2),
            o.twice(2),
            o.twice(2),
            o.twice(4),
        )
        self.assertEqual(results[0], 4)
        self.assertEqual(results[1], 4)
        self.assertEqual(results[2], 4)
        self.assertEqual(results[3], 8)
        excepted_call_count += 2
        self.assertEqual(o.call_count, excepted_call_count)

        # clear test (single)
        o.twice.clear(2)
        await asyncio.gather(
            o.twice(2),
            o.twice(4),
        )
        excepted_call_count += 1  # only dtwice(2) should have been called
        self.assertEqual(o.call_count, excepted_call_count)

        # clear test (all)
        o.twice.clear_all()
        await asyncio.gather(
            o.twice(2),
            o.twice(4),
        )
        excepted_call_count += 2  # both should have been called
        self.assertEqual(o.call_count, excepted_call_count)
