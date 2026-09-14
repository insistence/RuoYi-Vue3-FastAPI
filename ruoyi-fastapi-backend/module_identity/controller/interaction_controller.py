import json
from typing import Annotated, TypeVar

from fastapi import Depends, Header, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from config.env import OidcConfig
from exceptions.exception import OidcInteractionException
from module_identity.dependencies import require_oidc_protocol_ready
from module_identity.entity.vo.interaction_vo import (
    CaptchaResponseModel,
    ChangePasswordModel,
    InteractionConsentModel,
    InteractionLoginModel,
    InteractionResultModel,
    InteractionViewModel,
)
from module_identity.service.authorization_service import InteractionCompletionService
from module_identity.service.consent_service import InteractionConsentService
from module_identity.service.interaction_service import (
    InteractionFlowService,
    InteractionLoginOutcome,
    InteractionLoginService,
    InteractionService,
)
from module_identity.service.session_service import SsoSessionService
from utils.response_util import ResponseUtil

interaction_controller = APIRouterPro(
    tags=['认证中心交互'], order_num=5, dependencies=[Depends(require_oidc_protocol_ready)]
)
_MODEL = TypeVar('_MODEL', bound=BaseModel)
_MAX_INTERACTION_BODY_BYTES = 16 * 1024
_NO_STORE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}


def _redis(request: Request) -> Redis:
    """
    读取应用生命周期创建的 Redis 客户端

    :param request: 当前 HTTP 请求
    :return: 应用 Redis 客户端
    :raises OidcInteractionException: Redis 客户端不可用
    """

    value = getattr(request.app.state, 'redis', None)
    if value is None:
        raise OidcInteractionException(error='server_error', status_code=503, message='认证服务不可用')
    return value


def _client_ip(request: Request) -> str | None:
    """
    读取当前请求的客户端地址

    :param request: 当前 HTTP 请求
    :return: 客户端 IP 地址，不存在时返回 None
    """

    client = getattr(request, 'client', None)

    return getattr(client, 'host', None)


def _not_found() -> Response:
    """
    构造认证中心未启用时的响应

    :return: 认证中心未启用的 404 响应
    """

    return _failure_response('认证服务未启用', 404)


def _invalid_body() -> Response:
    """
    构造认证交互请求无效时的响应

    :return: 请求无效的 400 响应
    """

    return _failure_response('认证交互请求无效', 400)


def _failure_response(msg: str, status_code: int, headers: dict[str, str] | None = None) -> Response:
    """
    构造项目统一错误响应并保留安全 HTTP 状态码

    :param msg: 错误消息
    :param status_code: HTTP 状态码
    :param headers: 可选响应头
    :return: 统一错误响应
    """

    response = ResponseUtil.failure(msg=msg, headers=headers or _NO_STORE)
    response.status_code = status_code

    return response


def _login_response(outcome: InteractionLoginOutcome) -> Response:
    """
    构造认证登录或改密响应

    :param outcome: 登录流程结果
    :return: 统一认证响应
    """

    if outcome.failure_message is not None:
        return ResponseUtil.failure(msg=outcome.failure_message, headers=_NO_STORE)
    response = ResponseUtil.success(data=outcome.result, headers=_NO_STORE)
    if outcome.cookie is not None:
        SsoSessionService.parse_cookie(outcome.cookie)
        response.set_cookie(value=outcome.cookie, **SsoSessionService.cookie_parameters())
    return response


def _json_pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    """
    构造拒绝重复字段的 JSON 对象

    :param items: JSON 对象字段
    :return: 唯一字段组成的对象
    :raises ValueError: JSON 对象包含重复字段
    """

    result: dict[str, object] = {}
    for key, value in items:
        # 拒绝重复字段，避免不同解析器产生歧义
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


async def _safe_json_body(request: Request, model: type[_MODEL]) -> _MODEL:
    """
    读取并校验认证交互 JSON 请求体

    :param request: 当前 HTTP 请求
    :param model: 请求体模型类型
    :return: 校验后的请求体模型
    :raises OidcInteractionException: 请求体格式或内容无效
    """
    # 仅接受 JSON，避免协议请求被宽松解析
    content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if content_type != 'application/json':
        raise OidcInteractionException(error='invalid_request', status_code=400, message='Invalid interaction request')
    try:
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            if not isinstance(chunk, (bytes, bytearray)):
                raise ValueError('request body must be bytes')
            # 限制请求体大小，避免认证交互接口被大请求消耗资源
            size += len(chunk)
            if size > _MAX_INTERACTION_BODY_BYTES:
                raise ValueError('request body is too large')
            chunks.append(bytes(chunk))
        raw = b''.join(chunks)
    except Exception as exc:
        raise OidcInteractionException(
            error='invalid_request', status_code=400, message='Invalid interaction request'
        ) from exc
    if len(raw) > _MAX_INTERACTION_BODY_BYTES:
        raise OidcInteractionException(error='invalid_request', status_code=400, message='Invalid interaction request')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_json_pairs)
        if not isinstance(value, dict):
            raise ValueError('JSON body must be an object')
        return model.model_validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
        raise OidcInteractionException(
            error='invalid_request', status_code=400, message='Invalid interaction request'
        ) from exc


@interaction_controller.get(
    '/auth/interaction/{interaction_id}',
    summary='获取认证交互页面接口',
    description='用于获取认证交互页面信息',
    response_model=DataResponseModel[InteractionViewModel],
)
async def get_interaction(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    redis = _redis(request)
    await InteractionFlowService.csrf_record(redis, interaction_id, csrf_token)
    page = await InteractionService.get(redis, interaction_id, query_db)
    page['captchaEnabled'] = await InteractionFlowService.captcha_enabled(redis)

    return ResponseUtil.success(data=InteractionViewModel.model_validate(page), headers=_NO_STORE)


@interaction_controller.get(
    '/auth/interaction/{interaction_id}/captcha',
    summary='获取认证交互验证码接口',
    description='用于获取认证交互验证码',
    response_model=DataResponseModel[CaptchaResponseModel],
)
async def captcha(request: Request, interaction_id: str) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    outcome = await InteractionFlowService.captcha(_redis(request), interaction_id, _client_ip(request))
    if outcome.rate_limited:
        return _failure_response(
            '请求过于频繁，请稍后再试',
            429,
            {**_NO_STORE, 'Retry-After': str(outcome.retry_after)},
        )
    if outcome.unavailable:
        return _failure_response('认证服务暂不可用', 503)
    return ResponseUtil.success(data=outcome.result, headers=_NO_STORE)


@interaction_controller.post(
    '/auth/interaction/{interaction_id}/login',
    summary='提交认证中心登录接口',
    description='用于提交认证中心登录',
    response_model=DataResponseModel[InteractionResultModel],
)
async def login_endpoint(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    try:
        body = await _safe_json_body(request, InteractionLoginModel)
    except OidcInteractionException:
        return _invalid_body()
    outcome = await InteractionLoginService.login(
        _redis(request),
        interaction_id,
        body,
        query_db,
        csrf_token,
        _client_ip(request),
        request.headers.get('user-agent'),
    )

    return _login_response(outcome)


@interaction_controller.post(
    '/auth/interaction/{interaction_id}/change-password',
    summary='提交认证中心改密接口',
    description='用于提交认证中心密码修改',
    response_model=DataResponseModel[InteractionResultModel],
)
async def change_password_endpoint(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    try:
        body = await _safe_json_body(request, ChangePasswordModel)
    except OidcInteractionException:
        return _invalid_body()
    outcome = await InteractionLoginService.change_password(_redis(request), interaction_id, body, query_db, csrf_token)

    return _login_response(outcome)


@interaction_controller.post(
    '/auth/interaction/{interaction_id}/consent',
    summary='提交认证中心授权同意接口',
    description='用于提交认证中心授权同意',
    response_model=DataResponseModel[InteractionResultModel],
)
async def consent_endpoint(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    try:
        body = await _safe_json_body(request, InteractionConsentModel)
    except OidcInteractionException:
        return _invalid_body()
    result = await InteractionConsentService.consent(_redis(request), interaction_id, body, query_db, csrf_token)

    return ResponseUtil.success(data=result, headers=_NO_STORE)


@interaction_controller.post(
    '/auth/interaction/{interaction_id}/cancel',
    summary='取消认证中心授权接口',
    description='用于取消认证中心授权',
    response_model=DataResponseModel[InteractionResultModel],
)
async def cancel(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    result = await InteractionConsentService.cancel(_redis(request), interaction_id, query_db, csrf_token)

    return ResponseUtil.success(data=result, headers=_NO_STORE)


@interaction_controller.post(
    '/auth/interaction/{interaction_id}/complete',
    summary='完成认证中心交互接口',
    description='用于完成认证交互并返回外部客户端跳转地址',
    response_model=DataResponseModel[InteractionResultModel],
)
async def complete(
    request: Request,
    interaction_id: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _not_found()
    await InteractionFlowService.csrf_record(_redis(request), interaction_id, csrf_token)
    result = await InteractionCompletionService.complete(_redis(request), interaction_id, query_db)

    return ResponseUtil.success(
        data=InteractionResultModel(
            next_action='redirect',
            interaction_id=interaction_id,
            redirect_url=result.location,
        ),
        headers=_NO_STORE,
    )
