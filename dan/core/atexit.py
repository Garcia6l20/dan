from dan.core import asyncio


__cleaners = []


def register(coro):
    __cleaners.append(coro)


async def cleanup():
    async with asyncio.TaskGroup() as group:
        for cleaner in __cleaners:
            group.create_task(cleaner)
