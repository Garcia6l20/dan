from random import random
import shutil
from dan.core import asyncio
from dan.core.terminal import TermStream, write as term_write, manager as term_manager

import logging

logging.basicConfig(level=logging.DEBUG)


async def test_status(stream: TermStream, *args, **kwargs):
    await stream.status(*args, **kwargs)
    await asyncio.sleep(0.1)

async def main():
    logger = logging.getLogger('main')
    
    logger.info('start')

    w = shutil.get_terminal_size()[0]

    streams: list[TermStream] = [TermStream(f"output {ii}") for ii in range(5)]

    logger.debug('up all')
    logger.debug('very long debug string, ' * 50)

    streams[0].status('very long status, ' * 50)
    
    await asyncio.sleep(0.1)

    for ii, stream in enumerate(streams):
        stream.status("up")

    await asyncio.sleep(0.1)
    
    logger.debug('up evens')

    for ii, stream in enumerate(streams):
        if ii % 2 == 0:
            stream.status("up even")
        else:
            logger.error('test !' + '.' * w)

    await asyncio.sleep(0.1)
    
    logger.debug('up odds')

    for ii, stream in enumerate(streams):
        if ii % 2 != 0:
            stream.status("up odd")

    await asyncio.sleep(0.5)

    term_write('regular write')

    async def do_stuff(stream: TermStream, **kwargs):
        sub = stream.sub('sub')
        slog = logging.getLogger(stream.name)
        with sub.progress("doing stuff", **kwargs) as bar:
            for n in range(100):
                sub.status(f'item {n}')
                bar()
                slog.error('A' * int(stream.prefix_width * random() * 3))
                await asyncio.sleep(0.025)
        stream.status("done", timeout=1)
        del sub

    logger.debug('testing progresses')

    async with asyncio.TaskGroup() as g:
        for ii, stream in enumerate(streams):
            if ii % 2 == 0:
                g.create_task(do_stuff(stream, total=100))
            else:
                g.create_task(do_stuff(stream))

    logger.debug('testing task group')
    s = streams[3]
    async with s.task_group('task group') as g:
        async def do_stuff(ii):
            await asyncio.sleep(ii * 0.25)
        for ii in range(5):
            g.create_task(do_stuff(ii))

    logger.info('done')

    await asyncio.sleep(1.1)
    term_manager().stop()
    await asyncio.sleep(0.1)


asyncio.run(main())
