import hashlib
import json
import re
import secrets
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.requests import Request

from common.enums import RedisInitKeyConfig
from config.env import AppConfig
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from utils.jwt_util import JwtUtil

SESSION_SECONDS = 300
SESSION_KEY_PREFIX = 'plugin:browser-session:'
COOKIE_NAME_PREFIX = 'Plugin-Session-'
COOKIE_PATTERN = re.compile(r'^([a-f0-9]{64})\.([A-Za-z0-9_-]{43})$')
SAFE_ROOT_PATTERN = re.compile(r'^(?:/[A-Za-z0-9_-]+)*$')
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


class PluginBrowserSession(BaseModel):
    """
    Redis 内部记录；不作为 API 响应或日志字段。
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    plugin_id: str
    version: str
    main_key: str
    main_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    user_id: int = Field(gt=0)
    origin: str
    nonce: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    csrf: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


def _digest(value: str) -> str:
    """
    计算会话凭证或绑定信息的 SHA256 摘要。

    :param value: 待计算摘要的字符串
    :return: 十六进制 SHA256 摘要
    """
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def request_origin(request: Request) -> str:
    """
    仅使用 ASGI 服务器处理过的 scheme/Host，不自行信任代理头。

    :param request: 宿主 HTTP 请求或转换后的 WebSocket 请求
    :return: 转为小写的 HTTP 或 HTTPS 来源地址
    """
    scheme = {'ws': 'http', 'wss': 'https'}.get(request.url.scheme, request.url.scheme)
    return f'{scheme}://{request.url.netloc}'.lower()


def plugin_browser_base(request: Request, plugin_id: str) -> str:
    """
    发行接口处的 root_path 为宿主部署前缀，而非插件 Mount 前缀。

    :param request: 签发插件会话的宿主请求
    :param plugin_id: 插件 ID
    :return: 包含宿主部署前缀的插件浏览器入口路径
    """
    root = str(request.scope.get('root_path', '')).rstrip('/')
    if not SAFE_ROOT_PATTERN.fullmatch(root):
        raise ValueError('插件浏览器入口需要安全的部署 root_path')
    return f'{root}/apps/{plugin_id}/'


def _parse_record(raw: str | bytes | None) -> PluginBrowserSession:
    """
    解析 Redis 中的插件浏览器会话，拒绝过期或格式无效的记录。

    :param raw: Redis 返回的会话 JSON 字符串或字节串
    :return: 验证后的插件浏览器会话记录
    """
    if not raw:
        raise LookupError('插件会话已过期')
    try:
        return PluginBrowserSession.model_validate_json(raw)
    except ValidationError as exc:
        raise LookupError('插件会话无效') from exc


async def issue_browser_session(
    request: Request, *, plugin_id: str, version: str, main_token: str, user_id: int
) -> tuple[str, str, int]:
    """
    认证成功的控制器调用；返回 cookie、CSRF 和有效秒数。

    一条 Redis 记录同时承担索引与认证，NX 竞争后读取获胜记录，避免多标签
    签发覆盖 cookie/CSRF。主登录 token 仅用于即时检查，不存入插件记录。

    :param request: 已通过宿主认证的会话签发请求
    :param plugin_id: 插件 ID
    :param version: 当前插件版本
    :param main_token: 当前用户的宿主登录凭证
    :param user_id: 已认证的用户 ID
    :return: 插件 Cookie 值、CSRF 凭证和有效秒数
    """
    origin = request_origin(request)
    if request.headers.get('origin') not in (None, origin):
        raise PermissionError('插件会话只能从同源宿主签发')
    payload = JwtUtil.decode(main_token)
    if int(payload.get('user_id', 0)) != user_id:
        raise PermissionError('插件会话用户身份不匹配')
    subject = payload.get('session_id') if AppConfig.app_same_time_login else str(user_id)
    if not subject:
        raise LookupError('主登录缺少会话标识')
    main_key = f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{subject}'
    redis = request.app.state.redis
    current = await redis.get(main_key)
    if isinstance(current, bytes):
        current = current.decode('utf-8')
    if not isinstance(current, str) or not secrets.compare_digest(current, main_token):
        raise LookupError('主登录会话已失效')
    remaining = int(float(payload.get('exp', 0)) - time.time())
    seconds = min(SESSION_SECONDS, remaining)
    if seconds <= 0:
        raise LookupError('主登录会话已过期')
    main_digest = _digest(main_token)
    identity = json.dumps([main_digest, plugin_id, version, origin], separators=(',', ':'))
    scope_key = _digest(identity)
    key = f'{SESSION_KEY_PREFIX}{scope_key}'
    for _ in range(3):
        raw = await redis.get(key)
        if raw:
            record = _parse_record(raw)
            if (
                record.plugin_id != plugin_id
                or record.version != version
                or record.main_key != main_key
                or record.main_digest != main_digest
                or record.user_id != user_id
                or record.origin != origin
            ):
                raise LookupError('插件会话绑定无效')
            # GET 后旧记录可能到期并被其他标签的 NX 重建；不能把旧 nonce
            # 随较晚的响应写回 Cookie。重新读取确认续期的仍是当前记录。
            if await redis.expire(key, seconds) and await redis.get(key) == raw:
                return f'{scope_key}.{record.nonce}', record.csrf, seconds
        else:
            record = PluginBrowserSession(
                plugin_id=plugin_id,
                version=version,
                main_key=main_key,
                main_digest=main_digest,
                user_id=user_id,
                origin=origin,
                nonce=secrets.token_urlsafe(32),
                csrf=secrets.token_urlsafe(32),
            )
            if await redis.set(key, record.model_dump_json(), ex=seconds, nx=True):
                return f'{scope_key}.{record.nonce}', record.csrf, seconds
    raise LookupError('插件会话正在更新，请重试')


async def authenticate_browser_session(
    request: Request, *, plugin_id: str, version: str, query_db: Any, websocket: bool = False
) -> Any:
    """
    每次使用时回查宿主 token，再复用原有登录服务获取实时用户和权限。

    :param request: 携带插件 Cookie 的请求
    :param plugin_id: 插件 ID
    :param version: 当前插件版本
    :param query_db: 用于查询用户及权限的数据库会话
    :param websocket: 是否按 WebSocket 请求执行来源校验
    :return: 通过宿主身份及实时权限校验的当前用户
    """
    cookie = request.cookies.get(f'{COOKIE_NAME_PREFIX}{plugin_id}', '')
    matched = COOKIE_PATTERN.fullmatch(cookie)
    if matched is None:
        raise LookupError('缺少插件会话')
    scope_key, nonce = matched.groups()
    redis = request.app.state.redis
    record = _parse_record(await redis.get(f'{SESSION_KEY_PREFIX}{scope_key}'))
    if record.plugin_id != plugin_id or record.version != version:
        raise PermissionError('插件会话不适用于此插件或版本')
    if not secrets.compare_digest(record.nonce, nonce):
        raise LookupError('插件会话无效')
    origin = request_origin(request)
    supplied_origin = request.headers.get('origin')
    if record.origin != origin or (supplied_origin is not None and supplied_origin != origin):
        raise PermissionError('插件会话来源不匹配')
    if websocket or request.method not in SAFE_METHODS:
        if supplied_origin != origin:
            raise PermissionError('插件请求缺少同源 Origin')
        if not websocket and not secrets.compare_digest(request.headers.get('x-plugin-csrf', ''), record.csrf):
            raise PermissionError('插件请求 CSRF 校验失败')
    main_token = await redis.get(record.main_key)
    if isinstance(main_token, bytes):
        main_token = main_token.decode('utf-8')
    if not isinstance(main_token, str) or not secrets.compare_digest(_digest(main_token), record.main_digest):
        raise LookupError('主登录会话已失效')
    try:
        user = await LoginService.get_current_user_for_plugin_session(
            request=request, token=main_token, query_db=query_db
        )
    except AuthException as exc:
        raise LookupError('主登录会话已失效') from exc
    if user.user.user_id != record.user_id:
        raise PermissionError('插件会话用户身份不匹配')
    return user
