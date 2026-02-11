import asyncio
import ipaddress
import os
import socket
import uuid
from collections.abc import Callable

import psutil
from fastapi import FastAPI, Request, applications
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from redis import asyncio as aioredis

from config.env import AppConfig


class APIDocsUtil:
    """
    API文档工具类
    """

    # API文档URLs
    _OPENAPI_URL = '/openapi.json'
    _PROXY_OPENAPI_URL = '/proxy-openapi.json'
    _DOCS_URL = '/docs'
    _PROXY_DOCS_URL = '/proxy-docs'
    _REDOC_URL = '/redoc'
    _PROXY_REDOC_URL = '/proxy-redoc'
    _OAUTH2_REDIRECT_URL = '/docs/oauth2-redirect'
    _PROXY_OAUTH2_REDIRECT_URL = '/proxy-docs/oauth2-redirect'

    # 文档静态资源URLs
    DEFAULT_REDOC_JS_URL = 'https://registry.npmmirror.com/redoc/2/files/bundles/redoc.standalone.js'
    DEFAULT_REDOC_FAVICON_URL = 'https://fastapi.tiangolo.com/img/favicon.png'
    DEFAULT_SWAGGER_JS_URL = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui-bundle.js'
    DEFAULT_SWAGGER_CSS_URL = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui.css'
    DEFAULT_SWAGGER_FAVICON_URL = 'https://fastapi.tiangolo.com/img/favicon.png'

    @classmethod
    def proxy_openapi_url(cls) -> str:
        """
        代理OpenAPI文档URL
        """
        return cls._PROXY_OPENAPI_URL if not AppConfig.app_disable_swagger and not AppConfig.app_disable_redoc else None

    @classmethod
    def docs_url(cls) -> str:
        """
        文档URL
        """
        return cls._DOCS_URL

    @classmethod
    def proxy_docs_url(cls) -> str:
        """
        代理文档URL
        """
        return cls._PROXY_DOCS_URL if not AppConfig.app_disable_swagger else None

    @classmethod
    def redoc_url(cls) -> str:
        """
        ReDoc文档URL
        """
        return cls._REDOC_URL

    @classmethod
    def proxy_redoc_url(cls) -> str:
        """
        代理ReDoc文档URL
        """
        return cls._PROXY_REDOC_URL if not AppConfig.app_disable_redoc else None

    @classmethod
    def proxy_oauth2_redirect_url(cls) -> str:
        """
        代理OAuth2重定向URL
        """
        return cls._PROXY_OAUTH2_REDIRECT_URL if not AppConfig.app_disable_swagger else None

    @classmethod
    def setup_docs_static_resources(
        cls,
        redoc_js_url: str = DEFAULT_REDOC_JS_URL,
        redoc_favicon_url: str = DEFAULT_REDOC_FAVICON_URL,
        swagger_js_url: str = DEFAULT_SWAGGER_JS_URL,
        swagger_css_url: str = DEFAULT_SWAGGER_CSS_URL,
        swagger_favicon_url: str = DEFAULT_SWAGGER_FAVICON_URL,
    ) -> None:
        """
        配置文档静态资源

        :param redoc_js_url: 用于加载ReDoc JavaScript的URL
        :param redoc_favicon_url: ReDoc要使用的favicon的URL
        :param swagger_js_url: 用于加载Swagger UI JavaScript的URL
        :param swagger_css_url: 用于加载Swagger UI CSS的URL
        :param swagger_favicon_url: Swagger UI要使用的favicon的URL
        :return:
        """

        def redoc_monkey_patch(*args, **kwargs) -> HTMLResponse:
            return get_redoc_html(
                *args,
                **kwargs,
                redoc_js_url=redoc_js_url,
                redoc_favicon_url=redoc_favicon_url,
            )

        def swagger_ui_monkey_patch(*args, **kwargs) -> HTMLResponse:
            return get_swagger_ui_html(
                *args,
                **kwargs,
                swagger_js_url=swagger_js_url,
                swagger_css_url=swagger_css_url,
                swagger_favicon_url=swagger_favicon_url,
            )

        applications.get_redoc_html = redoc_monkey_patch
        applications.get_swagger_ui_html = swagger_ui_monkey_patch

    @classmethod
    def custom_api_docs_router(
        cls,
        app: FastAPI,
        redoc_js_url: str = DEFAULT_REDOC_JS_URL,
        redoc_favicon_url: str = DEFAULT_REDOC_FAVICON_URL,
        swagger_js_url: str = DEFAULT_SWAGGER_JS_URL,
        swagger_css_url: str = DEFAULT_SWAGGER_CSS_URL,
        swagger_favicon_url: str = DEFAULT_SWAGGER_FAVICON_URL,
    ) -> None:
        """
        自定义API文档路由

        :param app: FastAPI对象
        :param redoc_js_url: 用于加载ReDoc JavaScript的URL
        :param redoc_favicon_url: ReDoc要使用的favicon的URL
        :param swagger_js_url: 用于加载Swagger UI JavaScript的URL
        :param swagger_css_url: 用于加载Swagger UI CSS的URL
        :param swagger_favicon_url: Swagger UI要使用的favicon的URL
        :return:
        """

        async def custom_openapi(request: Request) -> JSONResponse:
            return await cls._custom_openapi(app)

        async def custom_redoc(request: Request) -> HTMLResponse:
            return await cls._custom_redoc(app, redoc_js_url, redoc_favicon_url)

        async def custom_swagger(request: Request) -> HTMLResponse:
            return await cls._custom_swagger(app, swagger_js_url, swagger_css_url, swagger_favicon_url)

        async def custom_swagger_ui_redirect(request: Request) -> HTMLResponse:
            return await cls._custom_swagger_ui_redirect(app, swagger_favicon_url)

        # 注册路由
        app.add_route(cls._OPENAPI_URL, custom_openapi, include_in_schema=False)
        cls._register_docs_routes(app, custom_swagger, custom_swagger_ui_redirect, custom_redoc)

    @classmethod
    async def _custom_openapi(cls, app: FastAPI) -> JSONResponse:
        """
        自定义 OpenAPI 路由处理函数

        :param app: FastAPI对象
        :return: openapi的json响应
        """
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            separate_input_output_schemas=app.separate_input_output_schemas,
            external_docs=app.openapi_external_docs,
        )
        return JSONResponse(openapi_schema)

    @classmethod
    async def _custom_redoc(
        cls,
        app: FastAPI,
        redoc_js_url: str,
        redoc_favicon_url: str,
    ) -> HTMLResponse:
        """
        自定义 ReDoc 路由处理函数

        :param app: FastAPI对象
        :param redoc_js_url: 用于加载ReDoc JavaScript的URL
        :param redoc_favicon_url: ReDoc要使用的favicon的URL
        :return: ReDoc HTML响应
        """
        if not AppConfig.app_disable_redoc:
            return get_redoc_html(
                openapi_url=cls._OPENAPI_URL,
                title=f'{app.title} - ReDoc',
                redoc_js_url=redoc_js_url,
                redoc_favicon_url=redoc_favicon_url,
            )
        return cls._get_disabled_html_content(
            f'{app.title} - ReDoc',
            'ReDoc',
            redoc_favicon_url,
        )

    @classmethod
    async def _custom_swagger(
        cls,
        app: FastAPI,
        swagger_js_url: str,
        swagger_css_url: str,
        swagger_favicon_url: str,
    ) -> HTMLResponse:
        """
        自定义 Swagger UI 路由处理函数

        :param app: FastAPI对象
        :param swagger_js_url: 用于加载Swagger UI JavaScript的URL
        :param swagger_css_url: 用于加载Swagger UI CSS的URL
        :param swagger_favicon_url: Swagger UI要使用的favicon的URL
        :return: Swagger UI HTML响应
        """
        if not AppConfig.app_disable_swagger:
            return get_swagger_ui_html(
                openapi_url=cls._OPENAPI_URL,
                title=f'{app.title} - Swagger UI',
                swagger_js_url=swagger_js_url,
                swagger_css_url=swagger_css_url,
                swagger_favicon_url=swagger_favicon_url,
                oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
                init_oauth=app.swagger_ui_init_oauth,
                swagger_ui_parameters=app.swagger_ui_parameters,
            )
        return cls._get_disabled_html_content(
            f'{app.title} - Swagger UI',
            'Swagger UI',
            swagger_favicon_url,
        )

    @classmethod
    async def _custom_swagger_ui_redirect(
        cls,
        app: FastAPI,
        swagger_favicon_url: str,
    ) -> HTMLResponse:
        """
        自定义 Swagger UI OAuth2 重定向路由处理函数

        :param app: FastAPI对象
        :param swagger_favicon_url: Swagger UI要使用的favicon的URL
        :return: Swagger UI OAuth2重定向HTML响应
        """
        if not AppConfig.app_disable_swagger:
            return get_swagger_ui_oauth2_redirect_html()
        return cls._get_disabled_html_content(
            f'{app.title} - Swagger UI OAuth2 Redirect',
            'Swagger UI OAuth2 Redirect',
            swagger_favicon_url,
        )

    @staticmethod
    def _get_disabled_html_content(title: str, name: str, favicon_url: str) -> HTMLResponse:
        """
        生成禁用文档的HTML内容

        :param title: 页面标题
        :param name: 文档名称
        :param favicon_url: 图标地址
        :return: 禁用文档HTML响应
        """
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>{title}</title>
        <!-- needed for adaptive design -->
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="shortcut icon" href="{favicon_url}">
        <!--
        {name} doesn't change outer page styles
        -->
        <style>
        body {{
            margin: 10px;
            padding: 0;
        }}
        </style>
        </head>
        <body>
        <noscript>
            {name} requires Javascript to function. Please enable it to browse the documentation.
        </noscript>
        <h1 style="color: #ff4d4f;">{name} has been disabled. Please enable it first.</h1>
        </body>
        </html>
        """
        return HTMLResponse(html)

    @classmethod
    def _register_docs_routes(
        cls, app: FastAPI, swagger_handler: Callable, redirect_handler: Callable, redoc_handler: Callable
    ) -> None:
        """
        注册文档路由

        :param app: FastAPI对象
        :param swagger_handler: Swagger UI 路由处理函数
        :param redirect_handler: Swagger UI OAuth2 重定向路由处理函数
        :param redoc_handler: ReDoc 路由处理函数
        :return:
        """
        swagger_urls: list[str] = (
            [cls._DOCS_URL] if not AppConfig.app_disable_swagger else [cls._DOCS_URL, cls._PROXY_DOCS_URL]
        )
        swagger_redirect_urls: list[str] = (
            [cls._OAUTH2_REDIRECT_URL]
            if not AppConfig.app_disable_swagger
            else [cls._OAUTH2_REDIRECT_URL, cls._PROXY_OAUTH2_REDIRECT_URL]
        )
        redoc_urls: list[str] = (
            [cls._REDOC_URL] if not AppConfig.app_disable_redoc else [cls._REDOC_URL, cls._PROXY_REDOC_URL]
        )

        for url in swagger_urls:
            app.add_route(url, swagger_handler, include_in_schema=False)
        for url in swagger_redirect_urls:
            app.add_route(url, redirect_handler, include_in_schema=False)
        for url in redoc_urls:
            app.add_route(url, redoc_handler, include_in_schema=False)


class StartupUtil:
    """
    启动门禁工具类
    """

    @classmethod
    async def acquire_startup_log_gate(
        cls, redis: aioredis.Redis, lock_key: str, worker_id: str, lock_expire_seconds: int
    ) -> bool:
        """
        获取启动日志门禁

        :param redis: Redis连接对象
        :param lock_key: 分布式锁key
        :param worker_id: 当前worker标识
        :param lock_expire_seconds: 锁过期时间
        :return: 是否获得启动日志输出权
        """
        acquired = await redis.set(lock_key, worker_id, nx=True, ex=lock_expire_seconds)
        if acquired:
            return True
        current_holder = await redis.get(lock_key)
        return current_holder == worker_id

    @classmethod
    def start_lock_renewal(
        cls,
        redis: aioredis.Redis,
        lock_key: str,
        worker_id: str,
        lock_expire_seconds: int,
        interval_seconds: int,
        on_lock_lost: Callable[[], None] | None = None,
    ) -> asyncio.Task:
        """
        启动分布式锁续期任务

        :param redis: Redis连接对象
        :param lock_key: 分布式锁key
        :param worker_id: 当前worker标识
        :param lock_expire_seconds: 锁过期时间
        :param interval_seconds: 续期间隔时间
        :param on_lock_lost: 失去锁时的回调
        :return: 异步任务对象
        """

        async def _loop() -> None:
            while True:
                try:
                    current_holder = await redis.get(lock_key)
                    if current_holder == worker_id:
                        await redis.expire(lock_key, lock_expire_seconds)
                        await asyncio.sleep(interval_seconds)
                        continue
                    if on_lock_lost:
                        on_lock_lost()
                    break
                except Exception:
                    await asyncio.sleep(interval_seconds)

        return asyncio.create_task(_loop())


class WorkerIdUtil:
    """
    Worker标识生成工具类
    """

    _worker_id: str | None = None

    @classmethod
    def get_worker_id(cls, configured_worker_id: str | None) -> str:
        """
        获取当前worker标识

        :param configured_worker_id: 配置的worker标识
        :return: 当前worker标识
        """
        if cls._worker_id:
            return cls._worker_id
        worker_id = configured_worker_id
        if not worker_id or worker_id.lower() == 'auto':
            worker_id = f'{os.getpid()}-{uuid.uuid4().hex[:6]}'
        cls._worker_id = worker_id
        return worker_id


class IPUtil:
    """
    IP工具类
    """

    _PREFERRED_DNS_HOSTS: tuple[str, str] = ('223.5.5.5', '8.8.8.8')
    _DNS_CONNECT_TIMEOUT = 1

    @classmethod
    def get_local_ip(cls) -> str:
        """
        获取本机Local IP
        """
        try:
            for snics in psutil.net_if_addrs().values():
                for snic in snics:
                    if snic.family == socket.AF_INET and snic.address.startswith('127.'):
                        return snic.address
        except Exception:
            pass

        return '127.0.0.1'

    @classmethod
    def get_network_ips(cls) -> list[str]:
        """
        获取本机Network IP列表
        """
        network_ips = []
        try:
            # 获取网卡状态
            stats = psutil.net_if_stats()
            for name, snics in psutil.net_if_addrs().items():
                # 过滤掉状态为DOWN的网卡
                if name in stats and not stats[name].isup:
                    continue

                for snic in snics:
                    if snic.family == socket.AF_INET:
                        try:
                            ip_obj = ipaddress.ip_address(snic.address)
                            if ip_obj.is_loopback or ip_obj.is_link_local:
                                continue
                            network_ips.append(snic.address)
                        except ValueError:
                            continue
        except Exception:
            pass

        # 优先显示首选出站IP
        preferred_ip = None
        for dns_host in cls._PREFERRED_DNS_HOSTS:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.settimeout(cls._DNS_CONNECT_TIMEOUT)
                    s.connect((dns_host, 80))
                    preferred_ip = s.getsockname()[0]
                    break
            except Exception:
                continue

        if preferred_ip:
            if preferred_ip in network_ips:
                network_ips.remove(preferred_ip)
            network_ips.insert(0, preferred_ip)

        if not network_ips:
            network_ips = ['127.0.0.1']

        return network_ips
