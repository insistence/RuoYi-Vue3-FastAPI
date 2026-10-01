import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import math
import re
import secrets
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit
from uuid import RFC_4122, UUID

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPublicNumbers
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class OidcUtil:
    """
    统一认证公共工具类。
    """

    _PROTOCOL_DESCRIPTION_PATTERN = re.compile(r'[\x20-\x21\x23-\x5B\x5D-\x7E]+')

    _ERROR_MESSAGES = {
        'invalid_request': '认证请求无效',
        'invalid_client': '客户端认证失败',
        'invalid_grant': '授权凭据无效或已过期',
        'unauthorized_client': '客户端无权使用当前授权方式',
        'unsupported_grant_type': '不支持当前授权类型',
        'invalid_scope': '请求的权限范围无效',
        'invalid_target': '请求的资源受众无效',
        'unsupported_response_type': '不支持当前授权响应类型',
        'unsupported_response_mode': '不支持当前授权响应模式',
        'access_denied': '授权请求被拒绝',
        'server_error': '认证服务处理失败',
        'temporarily_unavailable': '认证服务暂不可用',
        'invalid_token': '访问令牌无效',
        'insufficient_scope': '访问令牌的权限不足',
        'interaction_required': '需要重新完成认证交互',
        'login_required': '需要登录后继续',
        'consent_required': '需要用户确认授权',
        'account_selection_required': '需要选择登录账号',
        'not_found': '请求的认证资源不存在',
    }

    _DEFAULT_PROTOCOL_DESCRIPTIONS = {
        'invalid_request': 'Invalid request',
        'invalid_client': 'Client authentication failed',
        'invalid_grant': 'The authorization grant is invalid or expired',
        'unauthorized_client': 'Client is not authorized',
        'unsupported_grant_type': 'Grant type is not supported',
        'invalid_scope': 'Requested scope is invalid',
        'invalid_target': 'Requested resource is invalid',
        'unsupported_response_type': 'Response type is not supported',
        'unsupported_response_mode': 'Response mode is not supported',
        'access_denied': 'Access is denied',
        'server_error': 'Authorization service is unavailable',
        'temporarily_unavailable': 'Authorization service is temporarily unavailable',
        'invalid_token': 'Invalid access token',
        'insufficient_scope': 'Access token scope is insufficient',
        'interaction_required': 'Interaction is required',
        'login_required': 'Login is required',
        'consent_required': 'Consent is required',
        'account_selection_required': 'Account selection is required',
        'not_found': 'Resource is unavailable',
    }

    _DESCRIPTION_MESSAGES = {
        'A current login is required': '需要有效的当前登录状态',
        'A new authorization decision is required': '需要重新确认授权',
        'A resource audience is required for resource scope': '申请资源权限时必须指定资源受众',
        'A transaction coordinator is required': '缺少事务协调器',
        'Access to this application is blocked': '当前用户已被禁止访问此应用',
        'Application is unavailable; restart login': '应用已不可用，请返回应用重新登录',
        'Application permissions have changed; restart login': '应用权限已变更，请返回应用重新登录',
        'Authentication audit service is unavailable': '认证审计服务不可用',
        'Authentication service is unavailable': '认证服务不可用',
        'Authorization audit service is unavailable': '授权审计服务暂不可用',
        'Authorization code could not be completed': '授权码兑换未能完成',
        'Authorization code could not be created': '授权码创建失败',
        'Authorization code is invalid': '授权码无效',
        'Authorization code is invalid or expired': '授权码无效或已过期',
        'Authorization code is not allowed for this client': '当前客户端未启用授权码模式',
        'Authorization code state is invalid': '授权码状态无效',
        'Authorization completion failed': '完成授权失败',
        'Authorization parameters must be in the form body': '授权参数必须全部放在表单请求体中',
        'Authorization server is not ready': '认证中心尚未就绪',
        'Authorization service is unavailable': '授权服务暂不可用',
        'CSRF validation failed': 'CSRF 校验失败，请重新发起认证',
        'Client PKCE policy is weaker than provider policy': '客户端 PKCE 配置不符合认证中心的安全要求',
        'Client authentication failed': '客户端认证失败',
        'Client is inactive': '客户端已停用或不可用',
        'Client is not registered': '客户端未注册或已停用',
        'Consent is required': '需要用户确认授权',
        'Current login could not be verified': '无法验证当前登录状态',
        'Duplicate authorization parameter': '授权请求包含重复参数',
        'Interaction TTL is invalid': '认证交互有效期无效',
        'Interaction cache callback failed': '认证交互缓存更新回调执行失败',
        'Interaction could not be created': '认证交互创建失败',
        'Interaction has already completed': '认证交互已完成，请勿重复提交',
        'Interaction is invalid or expired': '认证交互无效或已过期',
        'Interaction is missing or expired': '认证交互不存在或已过期',
        'Interaction is no longer active': '认证交互已失效，请重新发起认证',
        'Interaction is not complete': '认证交互尚未完成',
        'Interaction state has changed': '认证交互状态已变更，请刷新后重试',
        'Interaction state is invalid': '认证交互状态无效',
        'Interaction transition failed': '认证交互状态更新失败',
        'Invalid authorization form': '授权请求表单无效',
        'Invalid authorization request': '授权请求无效',
        'Invalid interaction request': '认证交互请求无效',
        'Invalid request': '请求参数无效',
        'Invalid token request': '令牌请求无效',
        'Invalid validated redirect URI': '已验证的回调地址无效',
        'Login is required': '需要登录后继续',
        'OIDC provider is disabled': '统一认证服务未启用',
        'Only PKCE S256 is supported': '仅支持 PKCE S256 校验方式',
        'Only authorization code is supported': '仅支持授权码响应类型 code',
        'OpenID scope requires the sub claim': 'openid 权限必须包含用户主体声明 sub',
        'PKCE S256 code_challenge must contain 43 characters': 'PKCE S256 的 code_challenge 必须为 43 个字符',
        'Requested resource is not allowed for this client': '当前客户端无权访问所请求的资源',
        'Requested scope does not belong to the selected resource': '请求的权限范围不属于所选资源',
        'Requested scope is not allowed for this client': '当前客户端不允许申请所请求的权限范围',
        'Requested scope is not authorized': '请求的权限范围尚未获准',
        'Required scope cannot be removed': '必需的权限范围不能取消',
        'Resource is unavailable': '资源不可用',
        'Resource policy has changed': '资源访问策略已变更，请重新授权',
        'Response mode is not supported': '不支持当前授权响应模式',
        'Scope policy has changed': '权限范围策略已变更，请重新授权',
        'Submitted scope is not allowed': '提交的权限范围不在允许列表内',
        'The authorization grant is invalid or expired': '授权凭据无效或已过期',
        'The authorization grant is no longer valid': '原授权已失效，请重新授权',
        'Token endpoint is unavailable': '令牌服务暂不可用',
        'Token issuance is unavailable': '令牌签发服务暂不可用',
        'Token policy is unavailable': '令牌策略不可用',
        'Too many authorization requests': '授权请求过于频繁，请稍后重试',
        'User denied the authorization request': '用户已拒绝授权请求',
        'User identity mapping is unavailable': '用户身份映射暂不可用',
        'User identity version could not be updated': '用户身份安全版本更新失败',
        'Validated redirect URI is invalid': '已校验的回调地址无效',
        'Validated redirect URI is unavailable': '已校验的回调地址不可用',
        'client_id and redirect_uri are required': '必须提供 client_id 和 redirect_uri',
        'max_age must be non-negative': 'max_age 不得为负数',
        'nonce is required for OpenID Connect authorization': 'OpenID Connect 授权请求必须提供 nonce',
        'openid scope is required': '授权请求必须包含 openid 权限',
        'prompt contains an unsupported combination': 'prompt 包含不支持的参数组合',
        'redirect_uri is not registered': '登录回调地址 redirect_uri 未注册',
    }

    _PROTOCOL_DESCRIPTIONS = {message: description for description, message in _DESCRIPTION_MESSAGES.items()}

    _SENSITIVE_KEY = re.compile(
        r'(?:token|code|secret|cookie|password|passwd|credential|authorization|private[_-]?key|'
        r'pkce|verifier|nonce|client[_-]?assertion|assertion|access[_-]?token|refresh[_-]?token|'
        r'id[_-]?token|state)',
        re.IGNORECASE,
    )

    _SENSITIVE_VALUE = re.compile(
        r'(?i)(?:bearer\s+|basic\s+|(?:access|refresh|id)?[_-]?(?:token|secret|code|cookie|password|verifier)\s*[=:])'
    )

    _OPAQUE_CAPABILITY = re.compile(
        r'(?i)(?<![A-Za-z0-9_-])(?:'
        r'(?:rt1|ac1|ss1)\.[^.\s]{1,256}\.[^.\s]{1,4096}|'
        r'cs1\.[^.\s]{16,4096}(?:\.[^.\s]{1,256})?'
        r')(?![A-Za-z0-9_-])'
    )

    _JWT_PART_COUNT = 3

    _JWT_PART_MIN_LENGTH = 16

    _JWT_PART_MAX_LENGTH = 4096

    _COMPONENT_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,128}$')

    _SHA256_HEX_LENGTH = 64

    _ENCRYPTION_KDF_ITERATIONS = 310_000

    _SAFE_KID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$')

    _MIN_PEPPER_BYTES = 32
    _MAX_URI_LENGTH = 1000
    _DEVELOPMENT_HTTP_HOSTS = frozenset({'localhost', '127.0.0.1', '::1'})
    _USERINFO_AUDIENCE_SUFFIX = '/oauth2/userinfo'
    _ASCII_CONTROL_LIMIT = 0x20
    _MAX_USER_AGENT_LENGTH = 500
    _COOKIE_PARTS = 3
    _COOKIE_PREFIX = 'ss1'
    _COOKIE_SECRET_TEXT_LENGTH = 43
    _COOKIE_SECRET_BYTES = 32
    _S256_CHALLENGE = re.compile(r'[A-Za-z0-9_-]{43}')

    # 异常诊断与协议文案

    @classmethod
    def localized_oauth_message(cls, error: str, description: str | None) -> str:
        """
        返回中文异常诊断；未知协议描述按错误码提供安全的中文说明。

        :param error: OAuth 错误码
        :param description: 原始协议描述或中文诊断
        :return: 中文异常说明
        """
        if description:
            translated = cls._DESCRIPTION_MESSAGES.get(description)
            if translated is not None:
                return translated
            if any('\u4e00' <= char <= '\u9fff' for char in description):
                return description
        return cls._ERROR_MESSAGES.get(error, '认证请求处理失败')

    @classmethod
    def protocol_error_description(cls, error: str, description: str | None) -> str | None:
        """
        保留合法 ASCII 协议描述，将中文或不安全字符转换为协议允许的说明。

        :param error: OAuth 错误码
        :param description: 原始异常说明
        :return: 符合 OAuth 字符约束的描述或 None
        """
        if not description:
            return None
        if cls._PROTOCOL_DESCRIPTION_PATTERN.fullmatch(description):
            return description
        return cls._PROTOCOL_DESCRIPTIONS.get(
            description, cls._DEFAULT_PROTOCOL_DESCRIPTIONS.get(error, 'Authentication request failed')
        )

    # 基础数据、批量参数与认证声明

    @staticmethod
    def read_field(user: Any, name: str, default: Any = None) -> Any:
        """
        从 ORM 用户对象或字典读取字段

        :param user: SysUser ORM 记录或用户 Claim 字段映射
        :param name: 字段名称
        :param default: 字段缺省值
        :return: 读取的字段值
        """

        if isinstance(user, Mapping):
            return user.get(name, default)
        return getattr(user, name, default)

    @staticmethod
    def positive_int(value: Any, field: str) -> int:
        """
        校验正整数标量

        :param value: 待校验的正整数
        :param field: 字段名称
        :return: 校验后的正整数
        """

        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f'{field} 必须为正整数')
        return value

    @staticmethod
    def nonnegative_int(value: Any, field: str) -> int:
        """
        校验非负整数标量

        :param value: 待校验的非负整数
        :param field: 字段名称
        :return: 校验后的非负整数
        """

        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f'{field} 必须为非负整数')
        return value

    @staticmethod
    def nonempty_string(value: Any, field: str, limit: int) -> str:
        """
        校验非空字符串及长度

        :param value: 待校验的字符串
        :param field: 字段名称
        :param limit: 字符串的最大长度
        :return: 校验后的字符串
        """

        if not isinstance(value, str) or not value or len(value) > limit:
            raise ValueError(f'{field} 必须为非空字符串')
        return value

    @classmethod
    def string_list(cls, value: Any, field: str, limit: int) -> list[str]:
        """
        校验字符串列表并复制为 JSON 安全列表

        :param value: 待校验的字符串列表
        :param field: 字段名称
        :param limit: 字符串列表的最大长度
        :return: 校验后的字符串列表
        """

        if not isinstance(value, (list, tuple)) or len(value) > limit:
            raise ValueError(f'{field} 必须为符合长度限制的字符串列表')
        return [cls.nonempty_string(item, field, 500) for item in value]

    @staticmethod
    def json_list(value: Any) -> list[Any]:
        """
        将 Scope 或 Resource 字段规范化为列表

        :param value: JSON 编码的 Scope 或 Resource 列表值
        :return: Scope 或 Resource 元素列表；输入不是 JSON 数组时返回空列表
        """

        return list(value) if isinstance(value, (list, tuple)) else []

    @staticmethod
    def json_object_pairs(items: list[tuple[str, object]]) -> dict[str, object]:
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
                raise ValueError('JSON 请求体包含重复字段')
            result[key] = value
        return result

    @staticmethod
    def serialize_json(record: Mapping[str, Any], *, error_message: str) -> str:
        """
        生成稳定紧凑的 JSON，并拒绝不可序列化对象和非有限数字。

        :param record: 需要缓存的标量载荷
        :param error_message: 调用场景的中文错误说明
        :return: 按键排序的 JSON 字符串
        """
        try:
            return json.dumps(record, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(error_message) from exc

    @staticmethod
    def json_etag(payload: Mapping[str, Any]) -> str:
        """
        为 JWKS 响应计算稳定的强 ETag

        :param payload: 公开响应 JSON 映射
        :return: 带双引号的 SHA-256 ETag
        """

        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

        return '"' + hashlib.sha256(canonical).hexdigest() + '"'

    @staticmethod
    def actor_name(value: Any, *, error_message: str = '操作者不能为空') -> str:
        """
        校验操作者名称并按管理字段长度截断，保留原始空白语义。

        :param value: 待校验的操作者名称
        :param error_message: 名称不可用时的中文说明
        :return: 最多 64 个字符的操作者名称
        """
        if not isinstance(value, str) or not value.strip():
            raise ValueError(error_message)
        return value[:64]

    @staticmethod
    def split_batch(value: str, field_name: str, *, max_size: int, validate_all_first: bool = False) -> list[str]:
        """
        拆分批量路径标识，拒绝空值、路径字符、空白和重复项。

        :param value: 逗号分隔的参数
        :param field_name: 错误说明中的字段名称
        :param max_size: 允许的最大项目数量
        :param validate_all_first: 是否先校验全部格式再检查重复，保留调用场景的报错顺序
        :return: 去除首尾空白后的标识列表
        """
        items = value.split(',') if isinstance(value, str) else []
        if not items or len(items) > max_size:
            raise ValueError(f'{field_name} 参数无效')
        values = [item.strip() for item in items]

        def invalid(item: str) -> bool:
            return not item or '%' in item or '/' in item or '\\' in item or any(char.isspace() for char in item)

        if validate_all_first and any(invalid(item) for item in values):
            raise ValueError(f'{field_name} 参数无效')
        result: list[str] = []
        for item in values:
            if invalid(item):
                raise ValueError(f'{field_name} 参数无效')
            if item in result:
                raise ValueError(f'{field_name} 参数重复')
            result.append(item)
        return result

    @staticmethod
    def unique_codes(values: Iterable[str], field_name: str) -> list[str]:
        """
        校验权限或资源编码的边界空白，并保持输入顺序和重复项错误。

        :param values: 待校验的编码集合
        :param field_name: 中文错误说明中的字段名称
        :return: 保持原序的编码列表
        """
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip() or value.strip() != value:
                raise ValueError(f'{field_name} 包含无效的标识')
            if value in result:
                raise ValueError(f'{field_name} 不得包含重复项')
            result.append(value)
        return result

    @staticmethod
    def normalize_user_ids(values: Iterable[int], *, max_size: int) -> tuple[int, ...]:
        """
        校验、去重并排序用户 ID，确保批量锁顺序稳定

        :param values: 待校验的用户 ID 可迭代集合
        :param max_size: 去重后允许的最大用户数量
        :return: 排序去重后的用户 ID 元组
        """

        if isinstance(values, (str, bytes)):
            raise ValueError('用户编号列表必须全部为整数')
        result = tuple(sorted(set(values)))
        if not result or len(result) > max_size:
            raise ValueError('用户编号列表数量无效')
        if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in result):
            raise ValueError('用户编号列表必须全部为正整数')
        return result

    @staticmethod
    def is_trimmed_identifier(value: str, *, max_length: int) -> bool:
        """
        检查标识长度及首尾空白，保留内部字符。

        :param value: 待校验的 Session ID
        :param max_length: 标识最大长度
        :return: Session ID 是否有效
        """

        return isinstance(value, str) and 1 <= len(value) <= max_length and value.strip() == value

    @staticmethod
    def scope_set(scopes: str | Iterable[str] | None) -> set[str]:
        """
        将空格分隔或集合形式的 Scope 规范化

        :param scopes: 请求的 Scope 集合
        :return: 规范化 Scope 集合
        """

        if scopes is None:
            return set()
        if isinstance(scopes, str):
            return {item for item in scopes.split() if item}
        return {item for item in scopes if isinstance(item, str) and item}

    @staticmethod
    def normalize_audiences(value: Any) -> list[str]:
        """
        将 aud 声明规范化为去重列表

        :param value: OAuth Token 的 Audience 声明值
        :return: 去重后的 Audience 列表；格式非法时返回空列表
        """

        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item for item in values):
            return []
        return list(dict.fromkeys(values))

    @staticmethod
    def token_audiences(issuer: str, resources: Sequence[str]) -> list[str]:
        """
        将 aud 声明规范化为去重列表

        :param issuer: OIDC issuer URL
        :param resources: 已校验的 Resource audience 字符串序列
        :return: 包含 userinfo audience 和 Resource audience 的去重列表
        """

        result = [f'{issuer.rstrip("/")}{OidcUtil._USERINFO_AUDIENCE_SUFFIX}']
        result.extend(resources)

        return list(dict.fromkeys(result))

    @staticmethod
    def claim_numeric_date(value: Any) -> int | float | None:
        """
        将用户更新时间转换为 NumericDate

        :param value: 用户更新时间
        :return: NumericDate 时间戳或 None
        """

        if value is None or isinstance(value, (int, float)):
            return value
        timestamp = getattr(value, 'timestamp', None)

        return int(timestamp()) if callable(timestamp) else None

    @staticmethod
    def numeric_date(value: datetime | None) -> int | None:
        """
        将 datetime 转换为有限的 Unix 时间戳

        :param value: 可选的 Token 签发时间或过期时间
        :return: 有限的 Unix 时间戳；输入为空或时间戳非有限时返回 None
        """

        if value is None:
            return None
        timestamp = value.timestamp()

        return int(timestamp) if math.isfinite(timestamp) else None

    @staticmethod
    def requires_reauthentication(auth_time: datetime, max_age: int | None, now: datetime | None = None) -> bool:
        """
        纯函数判断 SSO 认证是否超过 max_age

        :param auth_time: SSO 认证时间
        :param max_age: 请求的最大认证年龄
        :param now: 可选当前时间
        :return: 超过 max_age 时为 True
        """

        # 时间工具依赖基础异常，延迟导入避免异常模块初始化时形成循环。
        from utils.time_util import TimezoneUtil  # noqa: PLC0415

        if max_age is None:
            return False
        if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age < 0:
            raise ValueError('max_age 必须为非负整数')
        current = TimezoneUtil.to_utc(now) if now is not None else TimezoneUtil.utc_now()
        auth = TimezoneUtil.to_utc(auth_time)

        return current.timestamp() - auth.timestamp() > max_age

    # URI、路径标识与交互参数

    @staticmethod
    def validate_path_identifier(value: str, field_name: str) -> str:
        """
        校验可安全放入单一路径段的管理标识

        :param value: 待校验的资源或权限标识
        :param field_name: 校验失败时展示的字段名称
        :return: 校验通过的管理标识
        """

        if (
            not isinstance(value, str)
            or not value
            or not value[0].isalnum()
            or any(not (char.isascii() and (char.isalnum() or char in '._:-')) for char in value)
        ):
            raise ValueError(f'{field_name} 必须符合路径标识的字符要求')
        return value

    @classmethod
    def is_valid_kid(cls, value: Any) -> bool:
        """
        检查签名密钥标识的字符集和长度。

        :param value: 待检查的标识
        :return: 是否满足原有安全路径规则
        """
        return isinstance(value, str) and cls._SAFE_KID_PATTERN.fullmatch(value) is not None

    @staticmethod
    def validate_registered_uri(uri_type: str, value: str) -> str:
        """
        校验注册 URI

        :param uri_type: 注册地址类型
        :param value: 待校验的完整注册地址
        :return: 校验通过的原始注册地址
        """

        if '*' in value:
            raise ValueError('地址不得包含通配符')
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('地址必须使用 HTTP 或 HTTPS 协议并包含主机名')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('地址不得包含用户名或密码')
        if parsed.fragment:
            raise ValueError('地址不得包含片段标识 fragment')
        if uri_type == 'backchannel_logout' and parsed.query:
            raise ValueError('后端退出通知地址不得包含查询参数')
        try:
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise ValueError('地址中的主机名或端口无效') from exc
        if not hostname:
            raise ValueError('地址必须包含主机名')
        if parsed.scheme == 'http' and hostname.lower() not in OidcUtil._DEVELOPMENT_HTTP_HOSTS:
            raise ValueError('HTTP 地址仅允许用于本机开发环境')
        if uri_type == 'cors_origin' and (parsed.path or parsed.query):
            raise ValueError('跨域来源只能包含协议、主机名和可选端口')
        return value

    @staticmethod
    def validate_resource_audience(audience: str, *, max_length: int) -> str:
        """
        校验 Resource audience URI

        :param audience: Resource audience
        :param max_length: URI 最大长度
        :return: 校验后的 Resource audience URI
        :raises ValueError: audience 不是无用户信息的绝对 HTTPS URI 时抛出
        """

        if not isinstance(audience, str) or not audience or len(audience) > max_length:
            raise ValueError('资源受众必须为非空地址')
        parsed = urlsplit(audience)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.fragment:
            raise ValueError('资源受众必须是无片段标识的绝对 HTTPS 地址')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('资源受众地址不得包含用户名或密码')
        try:
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise ValueError('资源受众地址的主机名或端口无效') from exc
        if not hostname:
            raise ValueError('资源受众地址必须包含主机名')
        return audience

    @staticmethod
    def is_safe_post_logout_uri(uri: Any) -> bool:
        """
        验证退出后重定向 URI 的安全格式

        :param uri: 回调 URI
        :return: URI 是否满足退出后重定向安全约束
        """

        if not isinstance(uri, str) or not uri or len(uri) > OidcUtil._MAX_URI_LENGTH or '*' in uri:
            return False
        try:
            parsed = urlsplit(uri)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False
        return bool(
            parsed.scheme in {'http', 'https'}
            and hostname
            and parsed.netloc
            and (parsed.scheme == 'https' or hostname.lower() in OidcUtil._DEVELOPMENT_HTTP_HOSTS)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )

    @staticmethod
    def is_public_ip(value: str) -> bool:
        """
        判断地址是否不属于回环、内网、链路本地或保留网段

        :param value: IPv4 或 IPv6 文本地址
        :return: 仅当地址可作为公网目标时返回 ``True``
        """

        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        )

    @staticmethod
    def parse_backchannel_uri(uri: object) -> tuple[str, int] | None:
        """
        解析并校验 Back-Channel URI 的非网络安全边界

        :param uri: 待校验的 URI
        :return: 合法时返回主机名和端口，否则返回 ``None``
        """

        if not isinstance(uri, str) or not uri or len(uri) > OidcUtil._MAX_URI_LENGTH or '*' in uri:
            return None
        try:
            parsed = urlsplit(uri)
            hostname = parsed.hostname
            username = parsed.username
            password = parsed.password
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme != 'https'
            or not parsed.netloc
            or not hostname
            or username
            or password
            or parsed.query
            or parsed.fragment
        ):
            return None
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not OidcUtil.is_public_ip(hostname):
            return None
        return hostname, port or 443

    @staticmethod
    def replace_query_parameters(
        uri: str,
        parameters: Sequence[tuple[str, str]],
        replaced_fields: Collection[str],
        *,
        fragment: str | None = None,
        doseq: bool = False,
    ) -> str:
        """
        替换指定查询参数，同时保留其他参数的顺序、重复项和空值。

        此方法只负责 URL 编码，调用方必须先完成回调注册和地址安全校验。

        :param uri: 原始地址
        :param parameters: 按顺序追加的参数
        :param replaced_fields: 必须从原地址移除的参数名称
        :param fragment: 显式指定片段，None 表示保留原片段
        :param doseq: 是否展开参数中的序列值
        :return: 重新编码后的地址
        """
        parsed = urlsplit(uri)
        query = [
            (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in replaced_fields
        ]
        query.extend(parameters)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query, doseq=doseq),
                parsed.fragment if fragment is None else fragment,
            )
        )

    @staticmethod
    def append_state(redirect_uri: str, state: str | None) -> str:
        """
        为已验证的退出回调地址附加状态参数

        :param redirect_uri: 服务端已验证的退出回调地址
        :param state: 原始退出状态参数
        :return: 附加状态参数后的回调地址
        """

        if state is None:
            return redirect_uri
        return OidcUtil.replace_query_parameters(redirect_uri, [('state', state)], {'state'})

    @staticmethod
    def interaction_url(base: str, interaction_id: str, csrf_token: str) -> str:
        """
        构建只把原始 CSRF 放入 URL Fragment 的交互地址

        :param base: 交互地址基址
        :param interaction_id: 交互流程标识
        :param csrf_token: CSRF Token
        :return: 交互页面 URL
        """

        parsed = urlsplit(base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query['interaction'] = interaction_id

        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), f'csrf={csrf_token}'))

    @staticmethod
    def normalize_prompt(value: str | None) -> str | None:
        """
        校验并规范化认证交互提示，拒绝重复值和非法组合。

        :param value: 空格分隔的 prompt 参数
        :return: 保持原顺序的规范化参数或 None
        """
        if value is None:
            return None
        prompts = value.split()
        if (
            not prompts
            or len(set(prompts)) != len(prompts)
            or any(item not in {'login', 'consent', 'none'} for item in prompts)
            or ('none' in prompts and len(prompts) > 1)
        ):
            raise ValueError('prompt 只能包含支持的值，且 none 不能与其他值组合')
        return ' '.join(prompts)

    @classmethod
    def is_s256_challenge(cls, value: Any) -> bool:
        """
        检查无填充 Base64URL 格式的 SHA-256 PKCE 挑战值。

        :param value: 待检查的挑战值
        :return: 是否恰好包含 43 个允许的 ASCII 字符
        """
        return isinstance(value, str) and cls._S256_CHALLENGE.fullmatch(value) is not None

    # 编码、摘要与凭据

    @staticmethod
    def base64url_encode(value: bytes) -> str:
        """
        将字节编码为无填充的 Base64URL 文本

        :param value: 待编码字节
        :return: 无填充的 Base64URL 文本
        """

        return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')

    @staticmethod
    def sha256_digest(value: str | bytes) -> str:
        """
        计算原始内容的 SHA-256 十六进制摘要，不规范化或截断输入。

        :param value: URI、一次性凭据等原始内容
        :return: 小写十六进制摘要
        """
        raw = value.encode('utf-8') if isinstance(value, str) else value
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def sha256_hex_digest(value: str | bytes) -> str:
        """
        校验已生成的 SHA-256 十六进制摘要

        :param value: 摘要文本或 ASCII 字节
        :return: 小写十六进制摘要
        :raises TypeError: 输入不是 str 或 bytes
        :raises ValueError: 摘要长度或字符集不正确
        """

        if not isinstance(value, (str, bytes)):
            raise TypeError('摘要必须为字符串或字节数据')
        if isinstance(value, bytes):
            try:
                value = value.decode('ascii')
            except UnicodeDecodeError as exc:
                raise ValueError('摘要必须是 SHA-256 十六进制字符串') from exc
        if len(value) != OidcUtil._SHA256_HEX_LENGTH:
            raise ValueError('摘要必须是 SHA-256 十六进制字符串')
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError('摘要必须是 SHA-256 十六进制字符串') from exc
        return value.lower()

    @staticmethod
    def hmac_sha256(value: str | bytes, key: str | bytes) -> str:
        """
        对已由调用方校验的内容和密钥计算 HMAC-SHA256 摘要。

        :param value: 原始字符串或字节数据
        :param key: 原始字符串或字节形式的密钥
        :return: 小写十六进制摘要
        """
        raw_value = value.encode('utf-8') if isinstance(value, str) else value
        raw_key = key.encode('utf-8') if isinstance(key, str) else key
        return hmac.new(raw_key, raw_value, hashlib.sha256).hexdigest()

    @staticmethod
    def access_token_hash(access_token: str) -> str:
        """
        计算 OIDC at_hash 值

        :param access_token: 待计算 OIDC at_hash 的 ASCII JWT Access Token 文本
        :return: SHA-256 前 128 bit 摘要的无填充 Base64URL 字符串
        """

        digest = hashlib.sha256(access_token.encode('ascii')).digest()[:16]

        return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')

    @staticmethod
    def csrf_digest(token: str, pepper: str) -> str:
        """
        使用独立 Pepper 生成 CSRF HMAC 摘要

        :param token: 原始 CSRF Token
        :param pepper: Token 摘要 Pepper
        :return: CSRF 摘要
        """

        if (
            not isinstance(token, str)
            or not isinstance(pepper, str)
            or len(pepper.encode()) < OidcUtil._MIN_PEPPER_BYTES
        ):
            raise ValueError('CSRF 摘要密钥至少需要 32 字节')
        return OidcUtil.hmac_sha256(token, pepper)

    @classmethod
    def credential_proof(
        cls, interaction_id: str, user_id: int, subject_id: str, auth_version: int, *, pepper: str
    ) -> str:
        """
        生成绑定交互、用户、主体和安全版本的凭据证明摘要。

        :param interaction_id: 交互标识
        :param user_id: 本地用户编号
        :param subject_id: 稳定身份主体标识
        :param auth_version: 身份安全版本
        :param pepper: 调用方提供的认证摘要密钥
        :return: 凭据证明摘要
        """
        return cls.hmac_sha256(f'{interaction_id}:{user_id}:{subject_id}:{auth_version}', pepper)

    @classmethod
    def logout_confirmation_digest(cls, sso_cookie: str | None, browser_nonce: str, pepper: str | bytes) -> str:
        """
        计算退出确认凭据的浏览器绑定摘要。

        :param sso_cookie: 首次退出请求携带的会话 Cookie
        :param browser_nonce: 绑定浏览器的一次性随机数
        :param pepper: 调用方提供的认证摘要密钥
        :return: 浏览器绑定摘要
        """
        return cls.hmac_sha256((sso_cookie or '') + '\\0' + browser_nonce, pepper)

    @classmethod
    def logout_rate_scope(cls, address: Any, pepper: str | bytes) -> str:
        """
        生成退出限流主体摘要，在认证配置尚未就绪时使用原有固定回退值。

        :param address: 客户端地址或匿名占位值
        :param pepper: 调用方读取的认证摘要密钥
        :return: 限流主体摘要
        """
        raw_pepper = pepper.encode() if isinstance(pepper, str) else pepper
        if not isinstance(raw_pepper, bytes) or len(raw_pepper) < cls._MIN_PEPPER_BYTES:
            raw_pepper = hashlib.sha256(b'oidc-logout-rate-limit-fallback').digest()
        return cls.hmac_sha256(str(address), raw_pepper)

    @classmethod
    def redis_key_component(cls, value: str | int, *, name: str = 'Redis Key 组件') -> str:
        """
        校验可作为 Key 路径组件的标识符

        :param value: 待校验的标识符
        :param name: 错误信息中的字段名称
        :return: 原样返回的安全组件
        :raises ValueError: 组件为空或包含路径/控制字符
        """

        component = str(value)
        if not cls._COMPONENT_PATTERN.fullmatch(component):
            raise ValueError(f'{name} 包含不允许的字符')
        return component

    @classmethod
    def hash_sensitive_identifier(cls, value: str | bytes, pepper: str | bytes) -> str:
        """
        使用独立 Pepper 对敏感标识生成 HMAC-SHA256 摘要

        :param value: 用户名、IP 等敏感标识
        :param pepper: 独立于 JWT/传输加密密钥的 Pepper，至少 32 bytes
        :return: 64 位小写 HMAC-SHA256 摘要
        :raises TypeError: 标识或 Pepper 类型错误
        :raises ValueError: Pepper 为空或长度不足
        """

        if not isinstance(value, (str, bytes)) or not isinstance(pepper, (str, bytes)):
            raise TypeError('敏感标识和摘要密钥必须为字符串或字节数据')
        raw_value = value.encode('utf-8') if isinstance(value, str) else value
        raw_pepper = pepper.encode('utf-8') if isinstance(pepper, str) else pepper
        if len(raw_pepper) < cls._MIN_PEPPER_BYTES:
            raise ValueError('敏感标识摘要密钥至少需要 32 字节')
        return cls.hmac_sha256(raw_value, raw_pepper)

    @staticmethod
    def parse_basic_credentials(authorization: str) -> tuple[str, str]:
        """
        解析 RFC 7617 Basic Header，不接受请求体 Secret 回退

        :param authorization: Authorization Header
        :return: 解码后的 client_id 与 client_secret
        :raises ValueError: Header、Base64 或凭据格式不合法
        """

        if not isinstance(authorization, str) or authorization[:6].lower() != 'basic ':
            raise ValueError('客户端认证信息无效')
        encoded = authorization[6:].strip()
        if not encoded:
            raise ValueError('客户端认证信息无效')
        try:
            decoded = base64.b64decode(encoded, validate=True).decode('utf-8')
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise ValueError('客户端认证信息无效') from None
        if ':' not in decoded:
            raise ValueError('客户端认证信息无效')
        client_id, client_secret = decoded.split(':', 1)
        # OAuth 表单客户端认证使用 application/x-www-form-urlencoded 约定
        # 该约定同时正确处理 client_id 中的空格与 Secret 中的百分号编码冒号
        client_id, client_secret = unquote_plus(client_id), unquote_plus(client_secret)
        if not client_id or not client_secret:
            raise ValueError('客户端认证信息无效')
        # RFC 7617 user-id 不能包含冒号，但分割后的 Secret 可以包含冒号
        if any(ord(char) < OidcUtil._ASCII_CONTROL_LIMIT for char in client_id):
            raise ValueError('客户端认证信息无效')
        return client_id, client_secret

    @staticmethod
    def generate_client_id() -> str:
        """
        生成带固定前缀的随机客户端标识。

        :return: cli_ 前缀的客户端标识
        """
        return f'cli_{secrets.token_urlsafe(24)}'

    @staticmethod
    def generate_client_secret() -> str:
        """
        生成仅应展示一次的高熵 Client Secret

        :return: 带 cs1 类型前缀的随机 Secret
        """

        return f'cs1.{secrets.token_urlsafe(32)}'

    @staticmethod
    def client_secret_hashes(client: Any, explicit: Iterable[str] | None = None) -> list[str]:
        """
        收集 Client 当前可用的 Secret 哈希

        :param client: Client 映射或对象
        :param explicit: 调用方显式提供的 Secret 哈希集合
        :return: 规范化后的 Secret 哈希列表
        """

        values = explicit
        if values is None:
            values = OidcUtil.read_field(client, 'secret_hashes')
        if values is None:
            values = OidcUtil.read_field(client, 'secrets')
        if values is None:
            one = OidcUtil.read_field(client, 'secret_hash')
            values = [one] if one else []
        result: list[str] = []
        for item in values:
            if isinstance(item, str):
                result.append(item)
            else:
                value = OidcUtil.read_field(item, 'secret_hash')
                if isinstance(value, str):
                    result.append(value)
        return result

    # 会话数据与审计脱敏

    @staticmethod
    def is_rfc4122_uuid(value: str) -> bool:
        """
        判断字符串是否为规范的 RFC 4122 UUID

        :param value: 待检查的 UUID 字符串
        :return: 是否为规范的 RFC 4122 UUID 字符串
        """

        try:
            parsed = UUID(value)
        except (TypeError, ValueError, AttributeError):
            return False
        return str(parsed) == value and parsed.variant == RFC_4122

    @staticmethod
    def parse_sso_cookie(cookie: str) -> tuple[str, str]:
        """
        拆分并验证 SSO Cookie 中的 Session 标识和随机 Secret

        :param cookie: Cookie 原文
        :return: ``(sid, secret)``
        :raises ValueError: Cookie 格式、UUID 或 Secret 长度不合法
        """

        if not isinstance(cookie, str):
            raise ValueError('会话 Cookie 必须为字符串')
        parts = cookie.split('.')
        if len(parts) != OidcUtil._COOKIE_PARTS or parts[0] != OidcUtil._COOKIE_PREFIX:
            raise ValueError('会话 Cookie 格式无效')
        sid, secret = parts[1], parts[2]
        if not OidcUtil.is_rfc4122_uuid(sid):
            raise ValueError('会话 Cookie 中的 sid 格式不规范')
        if len(secret) != OidcUtil._COOKIE_SECRET_TEXT_LENGTH or any(
            char not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for char in secret
        ):
            raise ValueError('会话 Cookie 密钥无效')
        try:
            decoded = base64.urlsafe_b64decode(secret + '===')
        except (binascii.Error, ValueError) as exc:
            raise ValueError('会话 Cookie 密钥无效') from exc
        if len(decoded) != OidcUtil._COOKIE_SECRET_BYTES:
            raise ValueError('会话 Cookie 密钥必须为 256 位')
        return sid, secret

    @staticmethod
    def session_pepper_bytes(pepper: str | bytes) -> bytes:
        """
        验证并转换 Token Pepper 字节串

        :param pepper: OIDC Token Pepper
        :return: Pepper 字节
        :raises ValueError: Pepper 类型或长度不合法
        """

        if not isinstance(pepper, (str, bytes)):
            raise ValueError('会话摘要密钥必须为字符串或字节数据')
        raw = pepper.encode() if isinstance(pepper, str) else pepper
        if len(raw) < OidcUtil._MIN_PEPPER_BYTES:
            raise ValueError('会话摘要密钥至少需要 32 字节')
        return raw

    @classmethod
    def session_secret_digest(cls, secret: str | bytes, pepper: str | bytes) -> str:
        """
        使用 Pepper 计算 Cookie Secret 的 HMAC 摘要

        :param secret: Cookie Secret 原文，仅在请求内存中存在
        :param pepper: OIDC Token Pepper
        :return: 十六进制 HMAC 摘要
        :raises ValueError: secret 不是 str/bytes，或 pepper 不是 str/bytes、编码后少于 32 字节
        """

        raw_secret = secret.encode() if isinstance(secret, str) else secret
        if not isinstance(raw_secret, bytes):
            raise ValueError('会话密钥必须为字节数据或字符串')
        return cls.hmac_sha256(raw_secret, cls.session_pepper_bytes(pepper))

    @classmethod
    def session_user_agent_digest(cls, user_agent: str | None, pepper: str | bytes) -> str | None:
        """
        使用 Pepper 计算 User-Agent 的 HMAC 摘要

        :param user_agent: 请求 User-Agent
        :param pepper: OIDC Token Pepper
        :return: User-Agent 摘要或 None
        :raises ValueError: User-Agent 不是字符串、超过 500 个字符，或 pepper 编码后少于 32 字节
        """

        if user_agent is None:
            return None
        if not isinstance(user_agent, str) or len(user_agent) > OidcUtil._MAX_USER_AGENT_LENGTH:
            raise ValueError('客户端标识 User-Agent 无效')
        return cls.session_secret_digest(user_agent, pepper)

    @staticmethod
    def looks_like_jwt(value: str) -> bool:
        """
        判断字符串是否具有 JWT 三段式秘密外观

        :param value: 待检测的字符串
        :return: 是否符合 JWT 外形
        """

        parts = value.split('.')

        return len(parts) == OidcUtil._JWT_PART_COUNT and all(
            OidcUtil._JWT_PART_MIN_LENGTH <= len(part) <= OidcUtil._JWT_PART_MAX_LENGTH for part in parts
        )

    @classmethod
    def sanitize_audit_detail(cls, detail: Any) -> Any:
        """
        递归删除审计详情中的敏感字段

        :param detail: 待记录的任意可序列化值
        :return: 只包含安全字段的可序列化值
        """

        if isinstance(detail, Mapping):
            return {
                str(key): cls.sanitize_audit_detail(value)
                for key, value in detail.items()
                if not cls._SENSITIVE_KEY.search(str(key))
            }
        if isinstance(detail, list):
            return [cls.sanitize_audit_detail(value) for value in detail]
        if isinstance(detail, tuple):
            return [cls.sanitize_audit_detail(value) for value in detail]
        if isinstance(detail, str):
            if (
                cls._SENSITIVE_VALUE.search(detail)
                or cls.looks_like_jwt(detail)
                or cls._OPAQUE_CAPABILITY.search(detail)
            ):
                return '[REDACTED]'
            return detail[:1024]
        if isinstance(detail, (int, float, bool)) or detail is None:
            return detail
        return None

    # RSA 公钥与签名私钥

    @staticmethod
    def rsa_public_jwk(public_key: RSAPublicKey, kid: str) -> dict[str, str]:
        """
        将 RSA 公钥编码为仅包含公开参数的 RS256 JWK。

        :param public_key: RSA 公钥
        :param kid: 已由调用方校验的密钥标识
        :return: 用于签名验证的公开 JWK
        """
        numbers = public_key.public_numbers()
        return {
            'kty': 'RSA',
            'use': 'sig',
            'kid': kid,
            'alg': 'RS256',
            'n': OidcUtil.base64url_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')),
            'e': OidcUtil.base64url_encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, 'big')),
        }

    @classmethod
    def normalize_public_jwk(
        cls, record: Any, *, min_rsa_bits: int = 2048, min_exponent: int = 3, max_exponent: int = 2**32
    ) -> dict[str, str]:
        """
        提取并校验公开 RSA JWK

        :param record: 数据库签名密钥记录或包含 public_jwk 字段的映射
        :param min_rsa_bits: 最小 RSA 模数位数
        :param min_exponent: 最小公开指数
        :param max_exponent: 公开指数上限（不包含）
        :return: 只包含公开字段的 JWK
        :raises ValueError: JWK 结构或算法不合法
        """

        value = getattr(record, 'public_jwk', record)
        if not isinstance(value, Mapping):
            raise ValueError('公开 JWK 必须为对象')
        if (
            getattr(record, 'key_use', 'sig') != 'sig'
            or getattr(record, 'alg', 'RS256') != 'RS256'
            or value.get('kty') != 'RSA'
            or value.get('use', 'sig') != 'sig'
            or value.get('alg', 'RS256') != 'RS256'
        ):
            raise ValueError('仅支持使用 RS256 签名的 RSA JWK')
        record_kid = getattr(record, 'kid', None)
        kid = value.get('kid', record_kid)
        if not cls.is_valid_kid(kid):
            raise ValueError('签名密钥标识 kid 包含不允许的字符')
        if record_kid is not None and kid != record_kid:
            raise ValueError('公开 JWK 的 kid 与数据库密钥标识不匹配')
        result = {field: value.get(field) for field in ('kty', 'use', 'kid', 'alg', 'n', 'e')}
        result.update({'kty': 'RSA', 'use': 'sig', 'kid': kid, 'alg': 'RS256'})
        if (
            not isinstance(result.get('n'), str)
            or not result['n']
            or not isinstance(result.get('e'), str)
            or not result['e']
        ):
            raise ValueError('公开 JWK 必须包含 n 和 e')
        try:
            n_bytes = base64.urlsafe_b64decode(result['n'] + '=' * (-len(result['n']) % 4))
            e_bytes = base64.urlsafe_b64decode(result['e'] + '=' * (-len(result['e']) % 4))
        except (TypeError, ValueError, binascii.Error) as exc:
            raise ValueError('公开 JWK 的 n/e 必须使用 Base64URL 编码') from exc
        if (
            not n_bytes
            or not e_bytes
            or n_bytes[0] == 0
            or cls.base64url_encode(n_bytes) != result['n']
            or cls.base64url_encode(e_bytes) != result['e']
        ):
            raise ValueError('公开 JWK 的 n/e 编码无效')
        modulus = int.from_bytes(n_bytes, 'big')
        exponent = int.from_bytes(e_bytes, 'big')
        if (
            modulus.bit_length() < min_rsa_bits
            or exponent < min_exponent
            or exponent >= max_exponent
            or exponent % 2 == 0
        ):
            raise ValueError('公开 JWK 的 RSA 参数无效')
        try:
            RSAPublicNumbers(exponent, modulus).public_key()
        except ValueError as exc:
            raise ValueError('公开 JWK 的 RSA 参数无效') from exc
        return result

    @staticmethod
    def derive_signing_encryption_key(material: bytes, salt: bytes) -> bytes:
        """
        使用随机盐派生私钥加密密钥

        :param material: 部署配置中的加密主密钥
        :param salt: 单条密钥记录的随机盐
        :return: AES-GCM 使用的 256 位密钥
        """

        return PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=OidcUtil._ENCRYPTION_KDF_ITERATIONS,
        ).derive(material)

    @classmethod
    def encrypt_signing_private_key(cls, pem: bytes, material: bytes, *, salt: bytes, nonce: bytes) -> str:
        """
        按现有 v2 格式封装使用 AES-GCM 加密的签名私钥。

        :param pem: 私钥 PEM 字节
        :param material: 调用方校验后的部署加密主密钥
        :param salt: 调用方生成的 16 字节随机盐
        :param nonce: 调用方生成的 12 字节随机数
        :return: 带 v2 前缀的私钥密文
        """
        encrypted = AESGCM(cls.derive_signing_encryption_key(material, salt)).encrypt(nonce, pem, None)
        return 'v2.' + base64.urlsafe_b64encode(b'salt' + salt + nonce + encrypted).decode()

    @classmethod
    def decrypt_signing_private_key(cls, ciphertext: str, material: bytes) -> bytes:
        """
        解密现有 v1/v2 私钥密文，保留历史数据格式兼容性。

        :param ciphertext: 带版本前缀的私钥密文
        :param material: 部署加密主密钥
        :return: 已解密的私钥 PEM 字节
        """
        if ciphertext.startswith('v2.'):
            envelope = base64.urlsafe_b64decode(ciphertext.removeprefix('v2.'))
            salt, nonce, encrypted = envelope[4:20], envelope[20:32], envelope[32:]
            key = cls.derive_signing_encryption_key(material, salt)
        elif ciphertext.startswith('v1.'):
            envelope = base64.urlsafe_b64decode(ciphertext.removeprefix('v1.'))
            nonce, encrypted = envelope[:12], envelope[12:]
            key = hashlib.sha256(material).digest()
        else:
            raise ValueError('不支持当前签名私钥密文格式')
        return AESGCM(key).decrypt(nonce, encrypted, None)
