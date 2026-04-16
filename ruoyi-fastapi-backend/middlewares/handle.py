from fastapi import FastAPI

from config.env import AppConfig
from middlewares.api_response_header_middleware import add_api_response_header_middleware
from middlewares.context_middleware import add_context_cleanup_middleware
from middlewares.cors_middleware import add_cors_middleware
from middlewares.demo_mode_middleware import add_demo_mode_middleware
from middlewares.gzip_middleware import add_gzip_middleware
from middlewares.trace_middleware import add_trace_middleware
from middlewares.transport_crypto_middleware import add_transport_crypto_middleware


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
    # 加载接口响应头追加中间件
    add_api_response_header_middleware(app)
    # 加载trace中间件
    add_trace_middleware(app)
    if AppConfig.app_demo_mode:
        # 加载演示模式中间件
        add_demo_mode_middleware(app)
    # 加载传输层请求解密/响应加密中间件
    add_transport_crypto_middleware(app)
