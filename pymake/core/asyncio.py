from asyncio import *

class OnceLock:
    def __init__(self) -> None:
        self.__done = False
        self.__lock = Lock()

    async def __aenter__(self):
        await self.__lock.acquire()
        return self.__done
   
    async def __aexit__(self, exc_type, exc, tb):
        self.__done = True
        self.__lock.release()
