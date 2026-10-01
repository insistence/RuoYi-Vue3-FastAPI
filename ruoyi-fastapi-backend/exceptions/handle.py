from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse as FastAPIJSONResponse
from fastapi.responses import RedirectResponse
from pydantic_validation_decorator import FieldValidationError

from exceptions.exception import (
    AuthException,
    FileRangeNotSatisfiableException,
    LoginException,
    ModelValidatorException,
    OAuthProtocolException,
    OidcInteractionException,
    PermissionException,
    ServiceException,
    ServiceWarning,
)
from utils.log_util import logger
from utils.oidc_util import OidcUtil
from utils.response_util import JSONResponse, ResponseUtil, jsonable_encoder

_OAUTH_RESPONSE_PARAMETER_NAMES = frozenset({'code', 'error', 'error_description', 'error_uri', 'iss', 'state'})


def handle_exception(app: FastAPI) -> None:
    """
    全局异常处理
    """

    # 自定义token检验异常
    @app.exception_handler(AuthException)
    async def auth_exception_handler(request: Request, exc: AuthException) -> Response:
        return ResponseUtil.unauthorized(data=exc.data, msg=exc.message)

    # 自定义OAuth协议异常
    @app.exception_handler(OAuthProtocolException)
    async def oauth_protocol_exception_handler(request: Request, exc: OAuthProtocolException) -> Response:
        if exc.can_redirect:
            return _build_oauth_redirect(exc)
        headers = {**exc.headers, 'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
        if exc.error == 'invalid_client' and exc.status_code == status.HTTP_401_UNAUTHORIZED:
            headers.setdefault('WWW-Authenticate', 'Basic realm="oauth2/token"')
        return FastAPIJSONResponse(
            content=exc.as_dict(),
            status_code=exc.status_code,
            headers=headers,
        )

    # 自定义OIDC认证交互异常
    @app.exception_handler(OidcInteractionException)
    async def oidc_interaction_exception_handler(request: Request, exc: OidcInteractionException) -> Response:
        safe_message = {
            'invalid_request': '认证交互请求无效',
            'interaction_required': '认证交互已过期或不可用',
            'login_required': '需要登录',
            'consent_required': '需要授权确认',
            'invalid_scope': '请求权限无效',
            'server_error': '认证服务暂不可用',
        }.get(exc.error, '认证交互无效或已过期')
        return ResponseUtil.failure(
            data=exc.interaction_id,
            msg=safe_message,
            headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
        )

    # 自定义登录检验异常
    @app.exception_handler(LoginException)
    async def login_exception_handler(request: Request, exc: LoginException) -> Response:
        return ResponseUtil.failure(data=exc.data, msg=exc.message)

    # 自定义模型检验异常
    @app.exception_handler(ModelValidatorException)
    async def model_validator_exception_handler(request: Request, exc: ModelValidatorException) -> Response:
        logger.warning(exc.message)
        return ResponseUtil.failure(data=exc.data, msg=exc.message)

    # 自定义字段检验异常
    @app.exception_handler(FieldValidationError)
    async def field_validation_error_handler(request: Request, exc: FieldValidationError) -> Response:
        logger.warning(exc.message)
        return ResponseUtil.failure(msg=exc.message)

    # 自定义权限检验异常
    @app.exception_handler(PermissionException)
    async def permission_exception_handler(request: Request, exc: PermissionException) -> Response:
        return ResponseUtil.forbidden(data=exc.data, msg=exc.message)

    # 自定义服务异常
    @app.exception_handler(ServiceException)
    async def service_exception_handler(request: Request, exc: ServiceException) -> Response:
        logger.error(exc.message)
        return ResponseUtil.error(data=exc.data, msg=exc.message)

    # 自定义服务警告
    @app.exception_handler(ServiceWarning)
    async def service_warning_handler(request: Request, exc: ServiceWarning) -> Response:
        logger.warning(exc.message)
        return ResponseUtil.failure(data=exc.data, msg=exc.message)

    # 文件Range范围不可满足异常
    @app.exception_handler(FileRangeNotSatisfiableException)
    async def file_range_not_satisfiable_exception_handler(
        request: Request,
        exc: FileRangeNotSatisfiableException,
    ) -> Response:
        return Response(
            status_code=416,
            headers={
                'Accept-Ranges': 'bytes',
                'Content-Range': f'bytes */{exc.file_size}',
                'Content-Length': '0',
            },
        )

    # 处理其他http请求异常
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
        return JSONResponse(
            content=jsonable_encoder({'code': exc.status_code, 'msg': exc.detail}), status_code=exc.status_code
        )

    # 处理其他异常
    @app.exception_handler(Exception)
    async def exception_handler(request: Request, exc: Exception) -> Response:
        logger.exception(exc)
        return ResponseUtil.error(msg=str(exc))


def _build_oauth_redirect(exc: OAuthProtocolException) -> Response:
    """
    构造安全的 OAuth 授权响应重定向。

    :param exc: 已完成 Redirect URI 精确注册校验的协议异常
    :return: 303 重定向或本地 400 标准错误响应
    """
    parsed = urlsplit(exc.redirect_uri or '')
    if parsed.fragment or not parsed.scheme or not parsed.netloc:
        return FastAPIJSONResponse(
            content={'error': 'server_error', 'error_description': 'Invalid validated redirect URI'},
            status_code=400,
            headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
        )
    params = [('error', exc.error)]
    if exc.error_description:
        params.append(('error_description', exc.error_description))
    if exc.state:
        params.append(('state', exc.state))
    if exc.issuer:
        params.append(('iss', exc.issuer))
    location = OidcUtil.replace_query_parameters(
        exc.redirect_uri or '', params, _OAUTH_RESPONSE_PARAMETER_NAMES, fragment='', doseq=True
    )
    return RedirectResponse(
        url=location,
        status_code=303,
        headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
    )
