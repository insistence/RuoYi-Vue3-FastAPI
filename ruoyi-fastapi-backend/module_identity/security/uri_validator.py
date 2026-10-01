import asyncio
import socket

from utils.oidc_util import OidcUtil


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

    return addresses if addresses and all(OidcUtil.is_public_ip(address) for address in addresses) else set()


async def is_safe_backchannel_uri(uri: object) -> bool:
    """
    校验 Back-Channel URI 结构并执行 DNS 公网重解析

    :param uri: 待校验的注册或发送 URI
    :return: 仅 HTTPS、无用户信息、查询、片段且 DNS 目标全部公网时返回 ``True``
    """

    parsed = OidcUtil.parse_backchannel_uri(uri)
    if parsed is None:
        return False
    hostname, port = parsed

    return bool(await public_dns_addresses(hostname, port))
