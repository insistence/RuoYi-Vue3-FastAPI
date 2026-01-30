from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, applications
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from common.router import auto_register_routers
from config.env import AppConfig
from config.get_db import init_create_table
from config.get_redis import RedisUtil
from config.get_scheduler import SchedulerUtil
from exceptions.handle import handle_exception
from middlewares.handle import handle_middleware
from sub_applications.handle import handle_sub_applications
from utils.common_util import IPUtil, worship
from utils.log_util import logger


# 生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f'⏰️ {AppConfig.app_name}开始启动')
    worship()
    await init_create_table()
    app.state.redis = await RedisUtil.create_redis_pool()
    await RedisUtil.init_sys_dict(app.state.redis)
    await RedisUtil.init_sys_config(app.state.redis)
    await SchedulerUtil.init_system_scheduler()
    logger.info(f'🚀 {AppConfig.app_name}启动成功')
    host = AppConfig.app_host
    port = AppConfig.app_port
    if host == '0.0.0.0':
        local_ip = IPUtil.get_local_ip()
        network_ips = IPUtil.get_network_ips()
    else:
        local_ip = host
        network_ips = [host]

    app_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}</cyan>']
    app_links.extend(f'📡 Network:  <cyan>http://{ip}:{port}</cyan>' for ip in network_ips)
    logger.opt(colors=True).info('💻 应用地址:\n' + '\n'.join(app_links))

    if not AppConfig.app_disable_swagger:
        swagger_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}/docs</cyan>']
        swagger_links.extend(f'📡 Network:  <cyan>http://{ip}:{port}/docs</cyan>' for ip in network_ips)
        logger.opt(colors=True).info('📄 Swagger文档:\n' + '\n'.join(swagger_links))

    if not AppConfig.app_disable_redoc:
        redoc_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}/redoc</cyan>']
        redoc_links.extend(f'📡 Network:  <cyan>http://{ip}:{port}/redoc</cyan>' for ip in network_ips)
        logger.opt(colors=True).info('📚 ReDoc文档:\n' + '\n'.join(redoc_links))
    yield
    await RedisUtil.close_redis_pool(app)
    await SchedulerUtil.close_system_scheduler()


def setup_docs_static_resources(
    redoc_js_url: str = 'https://registry.npmmirror.com/redoc/2/files/bundles/redoc.standalone.js',
    redoc_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
    swagger_js_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui-bundle.js',
    swagger_css_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui.css',
    swagger_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
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


def custom_api_docs_router(
    app: FastAPI,
    redoc_js_url: str = 'https://registry.npmmirror.com/redoc/2/files/bundles/redoc.standalone.js',
    redoc_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
    swagger_js_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui-bundle.js',
    swagger_css_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui.css',
    swagger_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
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

    openapi_url = '/openapi.json'

    async def custom_openapi(request: Request) -> JSONResponse:
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

    async def custom_redoc(request: Request) -> HTMLResponse:
        if not AppConfig.app_disable_redoc:
            return get_redoc_html(
                openapi_url=openapi_url,
                title=f'{app.title} - ReDoc',
                redoc_js_url=redoc_js_url,
                redoc_favicon_url=redoc_favicon_url,
            )
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>{app.title} - ReDoc</title>
        <!-- needed for adaptive design -->
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        """
        html += f"""
        <link rel="shortcut icon" href="{redoc_favicon_url}">
        <!--
        ReDoc doesn't change outer page styles
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
            ReDoc requires Javascript to function. Please enable it to browse the documentation.
        </noscript>
        <h1 style="color: #ff4d4f;">ReDoc has been disabled. Please enable it first.</h1>
        </body>
        </html>
        """
        return HTMLResponse(html)

    async def custom_swagger(request: Request) -> HTMLResponse:
        if not AppConfig.app_disable_swagger:
            return get_swagger_ui_html(
                openapi_url=openapi_url,
                title=f'{app.title} - Swagger UI',
                swagger_js_url=swagger_js_url,
                swagger_css_url=swagger_css_url,
                swagger_favicon_url=swagger_favicon_url,
                oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
                init_oauth=app.swagger_ui_init_oauth,
                swagger_ui_parameters=app.swagger_ui_parameters,
            )
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>{app.title} - Swagger UI</title>
        <!-- needed for adaptive design -->
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        """
        html += f"""
        <link rel="shortcut icon" href="{swagger_favicon_url}">
        <!--
        Swagger UI doesn't change outer page styles
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
            Swagger UI requires Javascript to function. Please enable it to browse the documentation.
        </noscript>
        <h1 style="color: #ff4d4f;">Swagger UI has been disabled. Please enable it first.</h1>
        </body>
        </html>
        """
        return HTMLResponse(html)

    async def custom_swagger_ui_redirect(request: Request) -> HTMLResponse:
        if not AppConfig.app_disable_swagger:
            return get_swagger_ui_oauth2_redirect_html()
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>{app.title} - Swagger UI OAuth2 Redirect</title>
        <!-- needed for adaptive design -->
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        """
        html += f"""
        <link rel="shortcut icon" href="{swagger_favicon_url}">
        <!--
        Swagger UI doesn't change outer page styles
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
            Swagger UI OAuth2 Redirect requires Javascript to function. Please enable it to browse the documentation.
        </noscript>
        <h1 style="color: #ff4d4f;">Swagger UI OAuth2 Redirect has been disabled. Please enable it first.</h1>
        </body>
        </html>
        """
        return HTMLResponse(html)

    app.add_route(openapi_url, custom_openapi, include_in_schema=False)
    swagger_urls = ['/docs'] if not AppConfig.app_disable_swagger else ['/docs', '/proxy-docs']
    swagger_redirect_urls = (
        ['/docs/oauth2-redirect']
        if not AppConfig.app_disable_swagger
        else ['/docs/oauth2-redirect', '/proxy-docs/oauth2-redirect']
    )
    redoc_urls = ['/redoc'] if not AppConfig.app_disable_redoc else ['/redoc', '/proxy-redoc']
    for swagger_url in swagger_urls:
        app.add_route(swagger_url, custom_swagger, include_in_schema=False)
    for swagger_redirect_url in swagger_redirect_urls:
        app.add_route(swagger_redirect_url, custom_swagger_ui_redirect, include_in_schema=False)
    for redoc_url in redoc_urls:
        app.add_route(redoc_url, custom_redoc, include_in_schema=False)


def create_app() -> FastAPI:
    """
    创建FastAPI应用

    :return: FastAPI对象
    """
    # 配置文档静态资源
    setup_docs_static_resources()
    # 初始化FastAPI对象
    app = FastAPI(
        title=AppConfig.app_name,
        description=f'{AppConfig.app_name}接口文档',
        version=AppConfig.app_version,
        lifespan=lifespan,
        openapi_url='/proxy-openapi.json'
        if not AppConfig.app_disable_swagger and not AppConfig.app_disable_redoc
        else None,
        docs_url='/proxy-docs' if not AppConfig.app_disable_swagger else None,
        redoc_url='/proxy-redoc' if not AppConfig.app_disable_redoc else None,
        swagger_ui_oauth2_redirect_url='/proxy-docs/oauth2-redirect',
    )

    # 自定义API文档路由，修复无法直接通过后端地址访问文档的问题
    custom_api_docs_router(app)

    # 挂载子应用
    handle_sub_applications(app)
    # 加载中间件处理方法
    handle_middleware(app)
    # 加载全局异常处理方法
    handle_exception(app)
    # 自动注册路由
    auto_register_routers(app)

    return app
