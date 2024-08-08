from fastapi import FastAPI
from middlewares.cors_middleware import add_cors_middleware
from middlewares.gzip_middleware import add_gzip_middleware


def handle_middleware(app: FastAPI):
    """
    全局中间件处理
    """
    # 加载跨域中间件
    add_cors_middleware(app)
    # 加载gzip压缩中间件
    add_gzip_middleware(app)
