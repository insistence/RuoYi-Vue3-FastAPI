from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app: FastAPI):
    # 前端页面url
    origins = [
        'http://localhost:80',
        'http://127.0.0.1:80',
    ]

    # 后台api允许跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
