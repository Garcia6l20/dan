from dan.core import asyncio
from dan.core.terminal import TermStream, TermManager


async def test_status(stream: TermStream, *args, **kwargs):
    await stream.status(*args, **kwargs)
    await asyncio.sleep(0.1)

async def main():
    manager = TermManager()

    streams = [manager.create(f"output {ii}") for ii in range(5)]

    for ii, stream in enumerate(streams):
        await stream.status("up")

    for ii, stream in enumerate(streams):
        if ii % 2 == 0:
            await stream.status("up even")

    await asyncio.sleep(1)

    for ii, stream in enumerate(streams):
        if ii % 2 != 0:
            await stream.status("up odd")

    await asyncio.sleep(1)

    await manager.write('regular output\n')

    for ii, stream in enumerate(streams):
        if ii % 2 == 0:
            async with stream.progress("doing stuff with total", total=10) as bar:
                for n in range(10):
                    await bar(status=f"item {n}")
                    await asyncio.sleep(0.125)
            timeout = None
        else:
            async with stream.progress("doing stuff without total") as bar:
                for n in range(10):
                    await bar()
                    await asyncio.sleep(0.125)
            timeout = 1

        await stream.status("done", timeout=timeout)

    await asyncio.sleep(1.1)

    manager.stop()


asyncio.run(main())
