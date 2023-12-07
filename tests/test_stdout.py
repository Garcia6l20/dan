from dan.core import asyncio
from dan.core.terminal import TermStream, write as term_write

import logging

logging.basicConfig(level=logging.DEBUG)


async def test_status(stream: TermStream, *args, **kwargs):
    await stream.status(*args, **kwargs)
    await asyncio.sleep(0.1)

async def main():
    logger = logging.getLogger('main')
    
    logger.info('start')

    streams = [TermStream(f"output {ii}") for ii in range(5)]

    logger.debug('up all')

    for ii, stream in enumerate(streams):
        await stream.status("up")

    logger.debug('up evens')

    for ii, stream in enumerate(streams):
        if ii % 2 == 0:
            await stream.status("up even")

    await asyncio.sleep(0.5)
    
    logger.debug('up odds')

    for ii, stream in enumerate(streams):
        if ii % 2 != 0:
            await stream.status("up odd")

    await asyncio.sleep(0.5)

    await term_write('regular write')

    async def do_stuff(stream: TermStream, **kwargs):
        async with stream.progress("doing stuff", **kwargs) as bar,\
                stream.toast() as toast:
            for n in range(100):
                await toast(f'item {n}')
                await bar()
                await asyncio.sleep(0.025)
        await stream.status("done", timeout=1)

    logger.debug('testing progesses')

    async with asyncio.TaskGroup() as g:
        for ii, stream in enumerate(streams):
            if ii % 2 == 0:
                g.create_task(do_stuff(stream, total=100))
            else:
                g.create_task(do_stuff(stream))

    logger.info('done')

    await asyncio.sleep(1.1)


asyncio.run(main())
