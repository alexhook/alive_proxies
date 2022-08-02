import argparse
import asyncio
import os
import re
import time
from asyncio.exceptions import TimeoutError, IncompleteReadError
from ssl import SSLError
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, ServerDisconnectedError
from aiohttp_socks import ProxyConnector
from python_socks._errors import ProxyConnectionError, ProxyError, ProxyTimeoutError

DATA_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PROXIES_FILE_PATH = os.path.join(DATA_FILES_PATH, 'proxies.txt')
ALIVE_PROXIES_FILE_NAME = 'alive_proxies.txt'

CHECKING_URL = 'https://google.com/'
CONNECTION_TIMEOUT = 10


def parse_args():
    parser = argparse.ArgumentParser(description='Process some integers.',
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('file', type=str, help='path to input file with proxies')
    parser.add_argument('-o', '--output', metavar='PATH', type=str, default=ALIVE_PROXIES_FILE_NAME,
                        help=f'path to output file with alive proxies (default: {ALIVE_PROXIES_FILE_NAME})')
    parser.add_argument('-u', '--url', type=str, help=f'checking url (default: {CHECKING_URL})', default=CHECKING_URL)
    parser.add_argument('-t', '--timeout', type=int, help=f'connection timeout (default: {CONNECTION_TIMEOUT} seconds)',
                        default=CONNECTION_TIMEOUT)
    parser.add_argument('-p', '--protocol', type=str, help='default proxies protocol')
    parser.add_argument('--read', metavar='TEMPLATE', help='template for parsing proxies data from input file',
                        dest='input_template', type=str)
    parser.add_argument('--write', metavar='TEMPLATE', dest='output_template', type=str,
                        help='template for writing proxies data to output file\najsndkjasndjkas\nasjdnajkdnsakjdasjk')
    parser.add_argument('--rmd', action='store_true', dest='remove_duplicates',
                        help='remove duplicated proxies from input file')


def parse_proxy_string(proxy: str, template: str) -> dict:
    assert template.count('ip') and template.count('port'), \
        f'The template "{template}" must contain "ip" and "port" arguments.'

    url_parts = ('protocol', 'ip', 'port', 'username', 'password')

    regex_template = template
    regex_template_base = '(?P<{}>.*)'

    for url_part in url_parts:
        if regex_template.count(url_part):
            regex_template = regex_template.replace(url_part, regex_template_base.format(url_part))

    regex = re.search(regex_template, proxy)
    if regex is None:
        raise ValueError(f'The template "{template}" does not match with proxy string "{proxy}".')

    prts = dict.fromkeys(url_parts)
    prts.update(regex.groupdict())

    return prts


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

    with open(PROXIES_FILE_PATH, 'w') as proxies_file, open(ALIVE_PROXIES_FILE_NAME, 'w') as alive_proxies_file:
        proxies_file.write('\n'.join(proxies))
        alive_proxies_file.write('\n'.join(sorted_alive_proxies))


if __name__ == '__main__':
    asyncio.run(main())
