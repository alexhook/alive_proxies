import asyncio
import os
import time
from asyncio.exceptions import TimeoutError, IncompleteReadError
from ssl import SSLError
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, ServerDisconnectedError
from aiohttp_socks import ProxyConnector
from python_socks._errors import ProxyConnectionError, ProxyError, ProxyTimeoutError

DATA_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PROXIES_FILE_PATH = os.path.join(DATA_FILES_PATH, 'proxies.txt')
ALIVE_PROXIES_FILE_PATH = os.path.join(DATA_FILES_PATH, 'alive_proxies.txt')

CHECKING_URL = 'https://google.com/'
CONNECTION_TIMEOUT = 10


async def check_proxy(proxy: str) -> tuple[str, float]:
    connector = ProxyConnector.from_url(proxy)
    session_timeout = ClientTimeout(sock_connect=CONNECTION_TIMEOUT)

    async with ClientSession(connector=connector, timeout=session_timeout) as session:
        start = time.time()
        try:
            await session.get(CHECKING_URL, timeout=CONNECTION_TIMEOUT)
        except (
                ProxyConnectionError, ConnectionResetError, ProxyError, ProxyTimeoutError,
                IncompleteReadError, TimeoutError, ServerDisconnectedError, SSLError,
        ):
            print(f'Proxy {proxy} is DEAD.')
            return proxy, 0
        else:
            response_time = time.time() - start

        prts = urlparse(proxy)
        proxy = f'{prts.scheme}\t{prts.hostname}\t{prts.port}'

        print(f'Proxy {proxy} is ALIVE.')
        return proxy, response_time


async def main() -> None:
    with open(PROXIES_FILE_PATH) as proxies_file:
        proxies = set(proxies_file.read().split('\n'))

    tasks = []
    for proxy in proxies:
        tasks.append(asyncio.create_task(check_proxy(proxy)))

    result = await asyncio.gather(*tasks)

    alive_proxies = [(proxy, response_time) for proxy, response_time in result if response_time > 0]
    sorted_alive_proxies = [proxy for proxy, _ in sorted(alive_proxies, key=lambda x: x[1])]

    with open(PROXIES_FILE_PATH, 'w') as proxies_file, open(ALIVE_PROXIES_FILE_PATH, 'w') as alive_proxies_file:
        proxies_file.write('\n'.join(proxies))
        alive_proxies_file.write('\n'.join(sorted_alive_proxies))


if __name__ == '__main__':
    asyncio.run(main())
