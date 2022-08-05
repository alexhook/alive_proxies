import argparse
import asyncio
import re
import time
from asyncio.exceptions import TimeoutError, IncompleteReadError
from ssl import SSLError
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, ServerDisconnectedError
from aiohttp_socks import ProxyConnector
from python_socks._errors import ProxyConnectionError, ProxyError, ProxyTimeoutError

ALIVE_PROXIES_FILE_NAME = 'alive_proxies.txt'

CHECKING_URL = 'https://google.com/'
CONNECTION_TIMEOUT = 10

URL_PARTS = ('protocol', 'ip', 'port', 'username', 'password')


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description='in progress...',
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-f', '--file', metavar='PATH', type=str, help='path to file with proxies',
                        dest='proxies_file_path', required=True)
    parser.add_argument('-o', '--output', metavar='PATH', type=str, default=ALIVE_PROXIES_FILE_NAME,
                        help=f'path to file to write alive proxies (default: {ALIVE_PROXIES_FILE_NAME})',
                        dest='alive_proxies_file_path')
    parser.add_argument('-u', '--url', type=str, help=f'checking url (default: {CHECKING_URL})', default=CHECKING_URL,
                        dest='checking_url')
    parser.add_argument('-t', '--timeout', type=int, help=f'connection timeout (default: {CONNECTION_TIMEOUT} seconds)',
                        default=CONNECTION_TIMEOUT, dest='connection_timeout')
    parser.add_argument('-p', '--protocol', type=str, help='default proxies protocol', dest='default_protocol')
    parser.add_argument('--read', metavar='TEMPLATE', help='template for parsing proxies data from input file',
                        dest='read_template', type=str)
    parser.add_argument('--write', metavar='TEMPLATE', dest='write_template', type=str,
                        help='template for writing proxies data to output file')
    parser.add_argument('--rmd', action='store_true', dest='remove_duplicates',
                        help='remove duplicated proxies from input file')

    return vars(parser.parse_args())


def get_proxy_url(proxy: str, template: str, default_protocol: str = None) -> str:
    assert template.count('ip') and template.count('port'), \
        f'The template "{template}" must contain "ip" and "port" arguments.'

    regex_template = template
    regex_template_base = '(?P<{}>.*)'

    for url_part in URL_PARTS:
        if regex_template.count(url_part):
            regex_template = regex_template.replace(url_part, regex_template_base.format(url_part))

    regex = re.search(regex_template, proxy)
    if regex is None:
        raise ValueError(f'The template "{template}" does not match with proxy string "{proxy}".')

    prts = dict.fromkeys(URL_PARTS[1:])
    prts.update(regex.groupdict())

    if not prts.setdefault('protocol', default_protocol):
        raise ValueError(
            f'Proxy "{proxy}" does not have a protocol argument and the default protocol has not been passed.')

    if prts['username'] and prts['password']:
        return f"{prts['protocol']}://{prts['username']}:{prts['password']}@{prts['ip']}:{prts['port']}"

    return f"{prts['protocol']}://{prts['ip']}:{prts['port']}"


def get_proxy_string(proxy: str, template: str) -> str:
    prts = urlparse(proxy)
    prts = {
        'protocol': prts.scheme,
        'username': prts.username,
        'password': prts.password,
        'ip': prts.hostname,
        'port': str(prts.port),
    }

    for template_prt, url_prt in prts.items():
        template = template.replace(template_prt, url_prt)

    return template


async def check_proxy(proxy_url: str, checking_url: str, connection_timeout: int) -> tuple[str, float]:
    connector = ProxyConnector.from_url(proxy_url)
    session_timeout = ClientTimeout(sock_connect=connection_timeout)

    async with ClientSession(connector=connector, timeout=session_timeout) as session:
        start = time.time()
        try:
            await session.get(checking_url, timeout=connection_timeout)
        except (
                ProxyConnectionError, ConnectionResetError, ProxyError, ProxyTimeoutError,
                IncompleteReadError, TimeoutError, ServerDisconnectedError, SSLError,
        ):
            print(f'Proxy {proxy_url} is DEAD.')
            return proxy_url, 0

        response_time = time.time() - start
        print(f'Proxy {proxy_url} is ALIVE.')

        return proxy_url, response_time


async def main(
        proxies_file_path: str,
        alive_proxies_file_path: str,
        checking_url: str,
        connection_timeout: int,
        default_protocol: str = None,
        remove_duplicates: bool = False,
        read_template: str = None,
        write_template: str = None,
) -> None:
    with open(proxies_file_path) as proxies_file:
        proxies = set(proxies_file.read().split('\n'))

    tasks = []
    for proxy in proxies:
        if read_template:
            proxy = get_proxy_url(proxy, read_template, default_protocol)
        else:
            url_prts = urlparse(proxy)
            if not url_prts.scheme and not url_prts.netloc:
                raise ValueError(f'Incorrect proxy url "{proxy}".')

        tasks.append(asyncio.create_task(check_proxy(proxy, checking_url, connection_timeout)))

    results = await asyncio.gather(*tasks)

    alive_proxies = [(proxy, response_time) for proxy, response_time in results if response_time > 0]
    sorted_alive_proxies = [proxy for proxy, _ in sorted(alive_proxies, key=lambda x: x[1])]

    template = write_template or read_template
    if template:
        sorted_alive_proxies = [get_proxy_string(proxy, template) for proxy in sorted_alive_proxies]

    with open(alive_proxies_file_path, 'w') as alive_proxies_file:
        alive_proxies_file.write('\n'.join(sorted_alive_proxies))

    if remove_duplicates:
        with open(proxies_file_path, 'w') as proxies_file:
            proxies_file.write('\n'.join(proxies))


if __name__ == '__main__':
    args = parse_args()
    asyncio.run(main(**args))
