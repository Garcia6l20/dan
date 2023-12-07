from dan.core import asyncio
from dan.core.terminal import TermStream, write as term_write


async def test_status(stream: TermStream, *args, **kwargs):
    await stream.status(*args, **kwargs)
    await asyncio.sleep(0.1)

async def main():
    streams = [TermStream(f"output {ii}") for ii in range(5)]

    for ii, stream in enumerate(streams):
        await stream.status("up")

    for ii, stream in enumerate(streams):
        if ii % 2 == 0:
            await stream.status("up even")

    await asyncio.sleep(0.5)

    for ii, stream in enumerate(streams):
        if ii % 2 != 0:
            await stream.status("up odd")

    await asyncio.sleep(0.5)

    await term_write('regular output\n')

    async def do_stuff(stream: TermStream, **kwargs):
        async with stream.progress("doing stuff", **kwargs) as bar,\
                stream.toast() as toast:
            for n in range(100):
                await toast(f'item {n}')
                await bar()
                await asyncio.sleep(0.025)
        await stream.status("done", timeout=1)

    async with asyncio.TaskGroup() as g:
        for ii, stream in enumerate(streams):
            if ii % 2 == 0:
                g.create_task(do_stuff(stream, total=100))
            else:
                g.create_task(do_stuff(stream))

    await asyncio.sleep(1.1)


asyncio.run(main())
