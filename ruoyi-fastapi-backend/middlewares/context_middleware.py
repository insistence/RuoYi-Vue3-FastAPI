from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from common.context import RequestContext
from utils.time_util import TimezoneUtil


class ContextCleanupMiddleware(BaseHTTPMiddleware):
    """
    上下文清理中间件
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        在每个请求处理完成后清理上下文信息
        """
        timezone_name = request.headers.get('X-Timezone')
        try:
            if timezone_name is not None:
                timezone_name = TimezoneUtil.validate_timezone_name(timezone_name)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={'code': 422, 'msg': 'X-Timezone必须是有效的IANA时区', 'success': False},
            )
        token = RequestContext.set_current_timezone(timezone_name)
        try:
            return await call_next(request)
        finally:
            RequestContext.clear_all()
            RequestContext.reset_current_timezone(token)


def add_context_cleanup_middleware(app: FastAPI) -> None:
    """
    添加上下文清理中间件

    :param app: FastAPI对象
    """
    app.add_middleware(ContextCleanupMiddleware)
