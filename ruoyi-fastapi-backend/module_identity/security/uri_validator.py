import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

_MAX_URI_LENGTH = 1000


def _is_public_ip(value: str) -> bool:
    """
    判断地址是否不属于回环、内网、链路本地或保留网段

    :param value: IPv4 或 IPv6 文本地址
    :return: 仅当地址可作为公网目标时返回 ``True``
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


async def public_dns_only(hostname: str, port: int) -> bool:
    """
    解析目标主机全部 A/AAAA 记录并拒绝任一受限地址

    :param hostname: 已从 URI 解析出的主机名
    :param port: 目标 TCP 端口
    :return: 解析成功且全部地址为公网地址时返回 ``True``
    """
    return bool(await public_dns_addresses(hostname, port))


async def public_dns_addresses(hostname: str, port: int) -> set[str]:
    """
    解析并返回本次连接允许固定使用的公网地址集合

    :param hostname: 已解析的主机名
    :param port: 目标 TCP 端口
    :return: 全部解析结果均安全时的地址集合，失败返回空集合
    """
    loop = asyncio.get_running_loop()
    try:
        records = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
        )
    except (OSError, socket.gaierror, ValueError):
        return set()
    addresses = {item[4][0] for item in records if item[4]}
    return addresses if addresses and all(_is_public_ip(address) for address in addresses) else set()


def parse_backchannel_uri(uri: object) -> tuple[str, int] | None:
    """
    解析并校验 Back-Channel URI 的非网络安全边界

    :param uri: 待校验的 URI
    :return: 合法时返回主机名和端口，否则返回 ``None``
    """
    if not isinstance(uri, str) or not uri or len(uri) > _MAX_URI_LENGTH or '*' in uri:
        return None
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != 'https'
        or not parsed.netloc
        or not hostname
        or username
        or password
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not _is_public_ip(hostname):
        return None
    return hostname, port or 443


async def is_safe_backchannel_uri(uri: object) -> bool:
    """
    校验 Back-Channel URI 结构并执行 DNS 公网重解析

    :param uri: 待校验的注册或发送 URI
    :return: 仅 HTTPS、无用户信息、查询、片段且 DNS 目标全部公网时返回 ``True``
    """
    parsed = parse_backchannel_uri(uri)
    if parsed is None:
        return False
    hostname, port = parsed
    return bool(await public_dns_addresses(hostname, port))
