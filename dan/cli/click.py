from click import *

import inspect
import asyncio

from dan import logging

class AsyncContext(Context):
    def invoke(__self, __callback, *args, **kwargs):
        ret = super().invoke(__callback, *args, **kwargs)
        if inspect.isawaitable(ret):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return ret  # must be awaited
            return loop.run_until_complete(ret)
        else:
            return ret


BaseCommand.context_class = AsyncContext

logger = logging.getLogger('cli')
