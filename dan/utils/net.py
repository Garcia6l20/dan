from pathlib import Path

import aiohttp
import socket

from dan.core import aiofiles

class Ping:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
    
    def ping(self, timeout = 0.5):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((self.host, self.port))
            s.close()
            return True
        except socket.error:
            s.close()
            return False


__has_network_connection = None
def has_network_connection(timeout = 0.5):
    global __has_network_connection
    if __has_network_connection is None:
        __has_network_connection = Ping(host='8.8.8.8', port=443).ping(timeout)
    return __has_network_connection

async def fetch_file(url, dest: Path, name: str = None, chunk_size=1024, progress=None):
    if name is None:
        name = dest.name
    timeout = aiohttp.ClientTimeout(
        total=30 * 60, connect=30, sock_connect=30, sock_read=None
    )
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                message = await resp.read()
                raise RuntimeError(f"unable to fetch {url}: {message.decode()}")
            size = int(resp.headers.get("content-length", 0))

            with progress(f"downloading {name}", total=size // 1024) as bar:
                async with aiofiles.open(dest, mode="wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        await f.write(chunk)
                        bar(len(chunk) // 1024)
