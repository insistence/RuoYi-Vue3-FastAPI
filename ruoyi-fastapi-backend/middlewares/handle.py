from fastapi import FastAPI

from middlewares.context_middleware import add_context_cleanup_middleware
from middlewares.cors_middleware import add_cors_middleware
from middlewares.gzip_middleware import add_gzip_middleware
from middlewares.trace_middleware import add_trace_middleware


def handle_middleware(app: FastAPI) -> None:
    """
    全局中间件处理
    """
    # 加载上下文清理中间件
    add_context_cleanup_middleware(app)
    # 加载跨域中间件
    add_cors_middleware(app)
    # 加载gzip压缩中间件
    add_gzip_middleware(app)
    # 加载trace中间件
    add_trace_middleware(app)
