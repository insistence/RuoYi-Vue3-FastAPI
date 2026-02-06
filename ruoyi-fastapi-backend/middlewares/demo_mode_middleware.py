from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from utils.log_util import logger
from utils.response_util import ResponseUtil


class DemoModeMiddleware(BaseHTTPMiddleware):
    """
    演示模式中间件
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        演示模式下拦截指定请求
        """
        url_path = str(request.url)
        method = request.method.lower()
        intercept_url_list = [
            'system/user',
            'system/role',
            'system/menu',
            'system/dept',
            'system/post',
            'system/dict',
            'system/config',
            'system/notice',
            'monitor/operlog',
            'monitor/logininfor',
            'monitor/online',
            'monitor/job',
            'monitor/jobLog',
            'monitor/cache',
            'ai/model',
            'ai/chat',
        ]

        for item in intercept_url_list:
            if (url_path.startswith(f'{request.base_url!s}{item}') and method != 'get') or url_path.startswith(
                (
                    f'{request.base_url!s}common',
                    f'{request.base_url!s}register',
                    f'{request.base_url!s}tool/gen/createTable',
                )
            ):
                operate_ip = request.headers.get('X-Forwarded-For')
                logger.warning(
                    '请求IP:{}||请求API:{}||请求方法:{}||请求结果:演示模式，不允许操作！', operate_ip, url_path, method
                )
                return ResponseUtil.failure(msg='演示模式，不允许操作！')
        response = await call_next(request)
        return response


def add_demo_mode_middleware(app: FastAPI) -> None:
    """
    添加演示模式中间件

    :param app: FastAPI对象
    """
    app.add_middleware(DemoModeMiddleware)
