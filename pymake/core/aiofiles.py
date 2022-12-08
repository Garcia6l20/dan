import asyncio
from aiofiles import *
from aiofiles import os

import os as sync_os

async def rmtree(path):
    for root, dirs, files in sync_os.walk(path, topdown=False):
        # f = "\n  - ".join(files)
        # d = "\n  - ".join(dirs)
        # print(f'{root}: \n  - {f}\n  - {d}')
        clean_files = [os.remove(
            sync_os.path.join(root, name)) for name in files]
        clean_dirs = [os.rmdir(
            sync_os.path.join(root, name)) for name in dirs]
        await asyncio.gather(*clean_files)
        await asyncio.gather(*clean_dirs)
    await os.rmdir(path)
