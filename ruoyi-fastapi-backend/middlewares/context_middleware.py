from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from common.context import RequestContext


class ContextCleanupMiddleware(BaseHTTPMiddleware):
    """
    上下文清理中间件
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        在每个请求处理完成后清理上下文信息
        """
        response = await call_next(request)
        # 请求处理完成后清理所有上下文变量
        RequestContext.clear_all()
        return response


def add_context_cleanup_middleware(app: FastAPI) -> None:
    """
    添加上下文清理中间件

    :param app: FastAPI对象
    """
    app.add_middleware(ContextCleanupMiddleware)
