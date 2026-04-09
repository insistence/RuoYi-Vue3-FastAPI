from collections.abc import Mapping

from fastapi import Request


class ApiResponseHeaderUtil:
    """
    接口响应头通用工具类
    """

    @classmethod
    def merge_headers(cls, request: Request, headers: Mapping[str, str] | None) -> None:
        """
        将响应头暂存到请求上下文中，供出站中间件统一追加

        :param request: 当前请求对象
        :param headers: 需要追加的响应头
        :return: None
        """
        if not headers:
            return

        api_response_headers = dict(getattr(request.state, 'api_response_headers', {}))
        api_response_headers.update(headers)
        request.state.api_response_headers = api_response_headers
