from fastapi import Request

from config.env import AppConfig


class ClientIPUtil:
    """
    客户端IP提取工具
    """

    @classmethod
    def get_client_ip(cls, request: Request) -> str:
        """
        获取客户端真实IP

        仅当请求来源命中可信代理列表，且可信代理跳数大于0时，才会解析
        X-Forwarded-For / X-Real-IP 请求头；否则回退到直接连接来源地址。

        :param request: 当前请求对象
        :return: 客户端IP
        """
        remote_addr = request.client.host if request.client else 'unknown'
        if AppConfig.app_trusted_proxy_hops <= 0:
            return remote_addr
        if not cls._should_trust_proxy_headers(remote_addr):
            return remote_addr

        forwarded_for = request.headers.get('X-Forwarded-For', '')
        if forwarded_for:
            forwarded_chain = [item.strip() for item in forwarded_for.split(',') if item.strip()]
            if forwarded_chain:
                if len(forwarded_chain) > AppConfig.app_trusted_proxy_hops:
                    return forwarded_chain[-(AppConfig.app_trusted_proxy_hops + 1)]
                return forwarded_chain[0]

        real_ip = request.headers.get('X-Real-IP', '').strip()
        if real_ip:
            return real_ip

        return remote_addr

    @classmethod
    def _should_trust_proxy_headers(cls, remote_addr: str) -> bool:
        """
        判断当前连接来源是否属于可信代理

        :param remote_addr: 与应用直接建立连接的来源IP
        :return: 是否信任代理头
        """
        trusted_proxy_ips = cls._get_trusted_proxy_ips()
        return '*' in trusted_proxy_ips or remote_addr in trusted_proxy_ips

    @classmethod
    def _get_trusted_proxy_ips(cls) -> set[str]:
        """
        获取可信代理IP集合

        :return: 可信代理IP集合
        """
        return {item.strip() for item in AppConfig.app_trusted_proxy_ips.split(',') if item.strip()}
