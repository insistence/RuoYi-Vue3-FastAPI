import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from common.enums import RedisInitKeyConfig
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException, OidcInteractionException, ServiceException
from module_admin.service.captcha_service import CaptchaService
from module_admin.service.user_service import UserService
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.entity.vo.interaction_vo import (
    CaptchaResponseModel,
    ChangePasswordModel,
    InteractionLoginModel,
    InteractionResultModel,
)
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.audit_service import AuditService
from module_identity.service.identity_service import (
    CredentialAuthenticationError,
    CredentialAuthenticationService,
    IdentitySecurityEventError,
    IdentitySecurityEventService,
    IdentitySubjectService,
)
from module_identity.service.infrastructure_service import (
    AfterCommitCoordinator,
    OidcRateLimiter,
    RateLimitExceeded,
    RateLimitUnavailable,
)
from module_identity.service.session_service import SsoSessionError, SsoSessionService
from utils.pwd_util import PwdUtil
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from module_identity.entity.do.oauth_client_do import SysOAuthClient
    from module_identity.entity.do.oauth_grant_do import SysSsoSession
    from module_identity.entity.do.oauth_resource_do import SysOAuthScope


_PUBLIC_SCOPE_DESCRIPTIONS = {
    'openid': '用于确认你的身份并登录应用。',
    'profile': '允许应用读取昵称、头像等基本资料。',
    'email': '允许应用读取你的电子邮箱。',
    'phone': '允许应用读取你的手机号码。',
    'roles': '允许应用读取已向它开放的角色信息。',
    'dept': '允许应用读取你的部门信息。',
    'offline_access': '浏览器关闭或登录到期后，仍允许应用在授权有效期内继续访问；你可以撤销授权。',
}


@dataclass(frozen=True, slots=True)
class InteractionCreated:
    """
    Interaction 创建结果的最小一次性返回值

    :ivar interaction_id: 新建 Interaction 标识
    :ivar csrf_token: 仅首次返回的原始 CSRF Token
    :ivar initial_status: 服务端决定的初始状态
    """

    interaction_id: str
    csrf_token: str
    initial_status: str


class InteractionService:
    """
    交互流程模块服务层

    Redis 只保存 CSRF 摘要；原始 CSRF 仅由创建接口返回一次。页面读取接口只返回
    白名单投影，不建立新 CSRF，也不返回授权协议内部绑定字段
    """

    _ALLOWED_STATUSES = frozenset(
        {'awaiting_login', 'awaiting_consent', 'password_change_required', 'completed', 'denied', 'expired'}
    )
    _TERMINAL_STATUSES = frozenset({'completed', 'denied', 'expired'})
    _TRANSITIONS = {
        'awaiting_login': frozenset({'awaiting_consent', 'password_change_required', 'completed', 'denied', 'expired'}),
        'awaiting_consent': frozenset({'completed', 'denied', 'expired'}),
        'password_change_required': frozenset({'awaiting_consent', 'completed', 'denied', 'expired'}),
    }
    _PROTECTED_FIELDS = frozenset({'requestedAt', 'csrfHash', 'version', 'interactionId'})
    _UPDATABLE_FIELDS = frozenset(
        {
            'authenticatedSid',
            'userId',
            'subjectId',
            'authVersion',
            'consentRequired',
            'scopes',
            'grantId',
            'credentialProofHash',
        }
    )
    _PROMPT_VALUES = frozenset({'none', 'login', 'consent'})
    _MIN_PEPPER_BYTES = 32
    _MAX_STATE_LENGTH = 1024
    _MAX_SCOPE_LENGTH = 500
    _MAX_SCOPES = 100
    _MAX_INTERACTION_ID_LENGTH = 128
    _MAX_GRANT_ID_LENGTH = 36
    _NO_TTL_RESULT = -5
    _TRANSITION_SCRIPT = """
local current_json = redis.call('GET', KEYS[1])
if not current_json then return -1 end
local ok, current = pcall(cjson.decode, current_json)
if not ok or type(current) ~= 'table' then return -4 end
if redis.call('PTTL', KEYS[1]) <= 0 then
    redis.call('DEL', KEYS[1])
    return -5
end
if tonumber(current.version) ~= tonumber(ARGV[1]) then return -2 end
local expected = cjson.decode(ARGV[2])
local matched = false
for _, status in ipairs(expected) do
    if current.status == status then matched = true break end
end
if not matched then return -3 end
redis.call('SET', KEYS[1], ARGV[3], 'KEEPTTL')
return 1
"""

    @classmethod
    async def create(
        cls,
        redis: Redis,
        payload: Mapping[str, Any],
        *,
        ttl_seconds: int | None = None,
        pepper: str | None = None,
    ) -> InteractionCreated:
        """
        创建短期 Interaction，并原子占用随机 ID

        :param redis: 异步 Redis 客户端
        :param payload: AuthorizationContext 生成的服务端白名单载荷
        :param ttl_seconds: 可选 Interaction TTL
        :param pepper: CSRF 摘要 Pepper，至少 32 bytes
        :return: 只含标识、原始 CSRF 和初始状态的冻结结果
        :raises OidcInteractionException: prompt=none 无法静默完成时抛出
        :raises ValueError: payload、Prompt 或 TTL 不合法时抛出
        """

        record = cls._validate_payload(payload)
        prompt = record['prompt']
        authenticated_sid = record.get('authenticatedSid')
        has_sso = bool(authenticated_sid)
        if 'none' in prompt and not has_sso:
            raise OidcInteractionException(message='Login is required', error='login_required', status_code=400)
        if 'none' in prompt and bool(record['consentRequired']):
            raise OidcInteractionException(message='Consent is required', error='consent_required', status_code=400)

        if 'login' in prompt or not has_sso:
            initial_status = 'awaiting_login'
        elif bool(record['consentRequired']):
            initial_status = 'awaiting_consent'
        else:
            initial_status = 'completed'

        interaction_id = str(uuid4())
        csrf_token = secrets.token_urlsafe(32)
        csrf_hash = cls._csrf_digest(csrf_token, pepper or OidcConfig.oidc_token_hash_pepper)
        record.update(
            {
                'interactionId': interaction_id,
                'requestedAt': datetime.now(timezone.utc).isoformat(),
                'csrfHash': csrf_hash,
                'status': initial_status,
                'version': 1,
            }
        )
        ttl = OidcConfig.oidc_interaction_ttl_seconds if ttl_seconds is None else ttl_seconds
        if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
            raise ValueError('interaction ttl must be a positive integer')
        created = await redis.set(OidcRedisKey.interaction(interaction_id), cls._serialize(record), ex=ttl, nx=True)
        if not created:
            raise OidcInteractionException(
                message='Interaction could not be created', error='server_error', status_code=500
            )
        return InteractionCreated(interaction_id, csrf_token, initial_status)

    @classmethod
    async def get(cls, redis: Redis, interaction_id: str, db: AsyncSession) -> dict[str, Any]:
        """
        从当前启用的应用及权限定义构建页面，不公开管理备注或协议内部字段

        :param redis: 异步 Redis 客户端
        :param interaction_id: Interaction 标识
        :param db: 默认平台数据库会话
        :return: 页面安全载荷
        :raises OidcInteractionException: Interaction 缺失、过期或状态损坏时抛出
        """

        record = await cls._get_record(redis, interaction_id)
        client = await OAuthClientDao.get_by_pk(db, record['clientPk'])
        if client is None or client.client_id != record['clientId']:
            raise OidcInteractionException(message='应用已不可用，请返回应用重新登录', status_code=400)
        scopes = {scope.scope_code: scope for scope in await OAuthClientDao.list_scopes(db, client.client_pk)}
        if not set(record['scopes']).issubset(scopes):
            raise OidcInteractionException(message='应用权限已变更，请返回应用重新登录', status_code=400)
        ttl = await redis.ttl(OidcRedisKey.interaction(interaction_id))

        return cls._page_projection(record, ttl, client, scopes)

    @classmethod
    async def get_record(cls, redis: Redis, interaction_id: str) -> dict[str, Any]:
        """
        获取仅供后端状态处理使用的完整 Interaction 记录

        :param redis: 异步 Redis 客户端
        :param interaction_id: Interaction 标识
        :return: 完整内部记录；调用方不得直接返回给页面
        :raises OidcInteractionException: Interaction 缺失或记录损坏时抛出
        """

        return await cls._get_record(redis, interaction_id)

    @classmethod
    async def transition(
        cls,
        redis: Redis,
        interaction_id: str,
        expected_statuses: Collection[str],
        target_status: str,
        updates: Mapping[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """
        使用 Redis Lua CAS 原子推进 Interaction 状态并保留 TTL

        :param redis: 异步 Redis 客户端
        :param interaction_id: Interaction 标识
        :param expected_statuses: 允许作为当前状态的集合
        :param target_status: 目标状态
        :param updates: 可更新的后端认证字段
        :param expected_version: 调用方读取状态时的版本号
        :return: 更新后的下一步动作与剩余 TTL；页面元数据由 get 读取
        :raises OidcInteractionException: Interaction 缺失或并发状态已变化时抛出
        :raises ValueError: 状态、字段或流转方向不合法时抛出
        """

        if target_status not in cls._ALLOWED_STATUSES:
            raise ValueError('unsupported Interaction target status')
        expected = set(expected_statuses)
        if not expected or not expected.issubset(cls._ALLOWED_STATUSES):
            raise ValueError('Interaction source statuses are invalid')
        if any(target_status not in cls._TRANSITIONS.get(status, frozenset()) for status in expected):
            raise ValueError('Interaction state transition is not allowed')
        changes = dict(updates or {})
        unsafe = cls._PROTECTED_FIELDS.intersection(changes)
        if unsafe:
            raise ValueError(f'Interaction protected fields cannot be updated: {sorted(unsafe)}')
        if not set(changes).issubset(cls._UPDATABLE_FIELDS):
            raise ValueError('Interaction update fields are not allowed')
        current = await cls._get_record(redis, interaction_id)
        compare_version = current.get('version') if expected_version is None else expected_version
        if not isinstance(compare_version, int) or isinstance(compare_version, bool) or compare_version <= 0:
            raise ValueError('Interaction expected version is invalid')
        next_record = dict(current)
        next_record.update(changes)
        next_record['status'] = target_status
        next_record['version'] = int(current.get('version', 0)) + 1
        cls._validate_record(next_record)
        serialized = cls._serialize(next_record)
        result = await redis.eval(
            cls._TRANSITION_SCRIPT,
            1,
            OidcRedisKey.interaction(interaction_id),
            compare_version,
            json.dumps(sorted(expected), separators=(',', ':')),
            serialized,
        )
        if result == 1:
            ttl = await redis.ttl(OidcRedisKey.interaction(interaction_id))
            return {
                'interactionId': interaction_id,
                'nextAction': cls._next_action(target_status),
                'expiresIn': max(0, int(ttl)),
            }
        if result == -1:
            raise OidcInteractionException(
                message='Interaction is missing or expired', error='invalid_request', status_code=404
            )
        if result in {-2, -3}:
            raise OidcInteractionException(
                message='Interaction state has changed', error='invalid_request', status_code=409
            )
        if result == cls._NO_TTL_RESULT:
            raise OidcInteractionException(
                message='Interaction TTL is invalid', error='invalid_request', status_code=404
            )
        raise OidcInteractionException(message='Interaction transition failed', error='server_error', status_code=500)

    @classmethod
    def verify_csrf(cls, record: Mapping[str, Any], csrf_token: str, *, pepper: str | None = None) -> bool:
        """
        使用恒定时间比较验证 Interaction CSRF

        :param record: 后端读取的完整 Interaction 记录
        :param csrf_token: 请求携带的原始 CSRF Token
        :param pepper: CSRF 摘要 Pepper
        :return: 摘要匹配时为 True
        """

        stored = record.get('csrfHash') if isinstance(record, Mapping) else None
        if not isinstance(stored, str) or not isinstance(csrf_token, str) or not csrf_token:
            return False
        try:
            actual = cls._csrf_digest(csrf_token, pepper or OidcConfig.oidc_token_hash_pepper)
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(actual, stored)

    @staticmethod
    def requires_reauthentication(auth_time: datetime, max_age: int | None, now: datetime | None = None) -> bool:
        """
        纯函数判断 SSO 认证是否超过 max_age

        :param auth_time: SSO 认证时间
        :param max_age: 请求的最大认证年龄
        :param now: 可选当前时间
        :return: 超过 max_age 时为 True
        """

        if max_age is None:
            return False
        if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age < 0:
            raise ValueError('max_age must be a non-negative integer')
        current = TimezoneUtil.to_utc(now) if now is not None else TimezoneUtil.utc_now()
        auth = TimezoneUtil.to_utc(auth_time)

        return current.timestamp() - auth.timestamp() > max_age

    @classmethod
    async def _get_record(cls, redis: Redis, interaction_id: str) -> dict[str, Any]:
        """
        读取并校验后端完整记录

        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :return: 通过校验的完整 Interaction 记录
        """

        if (
            not isinstance(interaction_id, str)
            or not interaction_id
            or len(interaction_id) > cls._MAX_INTERACTION_ID_LENGTH
        ):
            raise OidcInteractionException(
                message='Interaction is missing or expired', error='invalid_request', status_code=404
            )
        key = OidcRedisKey.interaction(interaction_id)
        value = await redis.get(key)
        if value is None:
            raise OidcInteractionException(
                message='Interaction is missing or expired', error='invalid_request', status_code=404
            )
        try:
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            record = json.loads(value)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            raise OidcInteractionException(
                message='Interaction state is invalid', error='server_error', status_code=500
            ) from None
        ttl = await redis.ttl(key)
        if ttl <= 0:
            await redis.delete(key)
            raise OidcInteractionException(
                message='Interaction is missing or expired', error='invalid_request', status_code=404
            )
        try:
            cls._validate_record(record)
        except ValueError as exc:
            raise OidcInteractionException(
                message='Interaction state is invalid', error='server_error', status_code=500
            ) from exc
        return record

    @classmethod
    def _validate_record(cls, record: Mapping[str, Any]) -> None:
        """
        校验 Redis 中 Interaction 的完整结构和身份字段组合

        :param record: 交互记录
        :return: None
        """

        if not isinstance(record, Mapping):
            raise ValueError('interaction record must be a mapping')
        required = {'interactionId', 'requestedAt', 'csrfHash', 'status', 'version'}
        if not required.issubset(record):
            raise ValueError('interaction record is incomplete')
        if not isinstance(record['status'], str) or record['status'] not in cls._ALLOWED_STATUSES:
            raise ValueError('interaction status is invalid')
        if not isinstance(record['version'], int) or isinstance(record['version'], bool) or record['version'] <= 0:
            raise ValueError('interaction version is invalid')
        if not isinstance(record['csrfHash'], str) or not re.fullmatch(r'[0-9a-f]{64}', record['csrfHash']):
            raise ValueError('interaction csrfHash is invalid')
        requested_at = record['requestedAt']
        if not isinstance(requested_at, str):
            raise ValueError('interaction requestedAt is invalid')
        try:
            parsed = datetime.fromisoformat(requested_at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('interaction requestedAt is invalid') from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError('interaction requestedAt must be UTC')
        cls._validate_payload(record)
        identity_values = [record.get('userId'), record.get('subjectId'), record.get('authVersion')]
        if any(value is not None for value in identity_values) and not all(
            value is not None for value in identity_values
        ):
            raise ValueError('interaction identity fields must be complete')

    @classmethod
    def _validate_payload(cls, payload: Mapping[str, Any]) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
        """
        校验 AuthorizationContext 生成的 Interaction 载荷

        :param payload: Interaction 载荷
        :return: 通过校验的交互载荷
        """

        if not isinstance(payload, Mapping):
            raise ValueError('interaction payload must be a mapping')
        allowed = {
            'interactionId',
            'requestedAt',
            'csrfHash',
            'status',
            'version',
            'clientPk',
            'clientId',
            'redirectUri',
            'responseType',
            'scopes',
            'resources',
            'state',
            'nonce',
            'codeChallenge',
            'codeChallengeMethod',
            'prompt',
            'maxAge',
            'consentRequired',
            'grantId',
            'authenticatedSid',
            'userId',
            'subjectId',
            'authVersion',
            'credentialProofHash',
        }
        if not set(payload).issubset(allowed):
            raise ValueError('interaction payload contains unknown fields')
        if 'interactionId' in payload and (
            not isinstance(payload['interactionId'], str)
            or not payload['interactionId']
            or len(payload['interactionId']) > cls._MAX_INTERACTION_ID_LENGTH
        ):
            raise ValueError('interactionId is invalid')
        required = {
            'clientPk',
            'clientId',
            'redirectUri',
            'responseType',
            'scopes',
            'resources',
            'state',
            'nonce',
            'codeChallenge',
            'codeChallengeMethod',
            'prompt',
            'maxAge',
            'consentRequired',
        }
        if not required.issubset(payload):
            raise ValueError('interaction payload is missing required fields')
        if (
            not isinstance(payload['clientPk'], int)
            or isinstance(payload['clientPk'], bool)
            or payload['clientPk'] <= 0
        ):
            raise ValueError('clientPk must be a positive integer')
        for field, limit in (('clientId', 64), ('redirectUri', 1000), ('nonce', 1024), ('codeChallenge', 128)):
            if not isinstance(payload[field], str) or not payload[field] or len(payload[field]) > limit:
                raise ValueError(f'{field} is invalid')
        if payload['responseType'] != 'code' or payload['codeChallengeMethod'] != 'S256':
            raise ValueError('unsupported Interaction protocol fields')
        if not isinstance(payload['codeChallenge'], str) or not re.fullmatch(
            r'[A-Za-z0-9_-]{43}', payload['codeChallenge']
        ):
            raise ValueError('codeChallenge is invalid')
        if (
            not isinstance(payload['scopes'], (list, tuple))
            or len(payload['scopes']) > cls._MAX_SCOPES
            or not all(isinstance(item, str) for item in payload['scopes'])
        ):
            raise ValueError('scopes must be a string list')
        if 'openid' not in payload['scopes'] or len(set(payload['scopes'])) != len(payload['scopes']):
            raise ValueError('scopes must include openid and contain no duplicates')
        if (
            not isinstance(payload['resources'], (list, tuple))
            or len(payload['resources']) > 1
            or not all(isinstance(item, str) for item in payload['resources'])
        ):
            raise ValueError('resources must contain at most one string')
        if (
            'grantId' in payload
            and payload['grantId'] is not None
            and (
                not isinstance(payload['grantId'], str)
                or not payload['grantId']
                or len(payload['grantId']) > cls._MAX_GRANT_ID_LENGTH
            )
        ):
            raise ValueError('grantId is invalid')
        if any(not item or len(item) > cls._MAX_SCOPE_LENGTH for item in (*payload['scopes'], *payload['resources'])):
            raise ValueError('scope or resource value is invalid')
        if payload['state'] is not None and (
            not isinstance(payload['state'], str) or len(payload['state']) > cls._MAX_STATE_LENGTH
        ):
            raise ValueError('state is invalid')
        if payload['maxAge'] is not None and (
            not isinstance(payload['maxAge'], int) or isinstance(payload['maxAge'], bool) or payload['maxAge'] < 0
        ):
            raise ValueError('maxAge is invalid')
        if not isinstance(payload['consentRequired'], bool):
            raise ValueError('consentRequired is invalid')
        for field, limit in (('authenticatedSid', 36), ('subjectId', 36)):
            if (
                field in payload
                and payload[field] is not None
                and (not isinstance(payload[field], str) or not payload[field] or len(payload[field]) > limit)
            ):
                raise ValueError(f'{field} is invalid')
        if (
            'userId' in payload
            and payload['userId'] is not None
            and (
                not isinstance(payload['userId'], int) or isinstance(payload['userId'], bool) or payload['userId'] <= 0
            )
        ):
            raise ValueError('userId is invalid')
        if (
            'authVersion' in payload
            and payload['authVersion'] is not None
            and (
                not isinstance(payload['authVersion'], int)
                or isinstance(payload['authVersion'], bool)
                or payload['authVersion'] < 0
            )
        ):
            raise ValueError('authVersion is invalid')
        if (
            'credentialProofHash' in payload
            and payload['credentialProofHash'] is not None
            and (
                not isinstance(payload['credentialProofHash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', payload['credentialProofHash'])
            )
        ):
            raise ValueError('credentialProofHash is invalid')
        prompt = payload['prompt']
        if prompt is None:
            prompts: list[str] = []
        elif isinstance(prompt, str):
            prompts = prompt.split()
        elif isinstance(prompt, (list, tuple)) and all(isinstance(item, str) for item in prompt):
            prompts = list(prompt)
        else:
            raise ValueError('prompt is invalid')
        if (
            len(set(prompts)) != len(prompts)
            or any(item not in cls._PROMPT_VALUES for item in prompts)
            or ('none' in prompts and len(prompts) > 1)
        ):
            raise ValueError('prompt combination is invalid')
        result = dict(payload)
        result['scopes'] = list(payload['scopes'])
        result['resources'] = list(payload['resources'])
        result['prompt'] = prompts
        if 'authenticatedSid' not in result:
            result['authenticatedSid'] = None
        return result

    @staticmethod
    def _csrf_digest(token: str, pepper: str) -> str:
        """
        使用独立 Pepper 生成 CSRF HMAC 摘要

        :param token: 原始 CSRF Token
        :param pepper: Token 摘要 Pepper
        :return: CSRF 摘要
        """

        if (
            not isinstance(token, str)
            or not isinstance(pepper, str)
            or len(pepper.encode()) < InteractionService._MIN_PEPPER_BYTES
        ):
            raise ValueError('CSRF Pepper must contain at least 32 bytes')
        return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _serialize(record: Mapping[str, Any]) -> str:
        """
        生成稳定 JSON，拒绝 ORM 或任意不可序列化对象

        :param record: 交互记录
        :return: 序列化 JSON 字符串
        """

        try:
            return json.dumps(record, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('interaction payload must be JSON serializable') from exc

    @staticmethod
    def _next_action(status: str) -> str:
        """
        将内部交互状态转换为页面的下一步动作

        :param status: 当前交互状态
        :return: 页面下一步动作
        """

        return {
            'awaiting_login': 'login',
            'awaiting_consent': 'consent',
            'password_change_required': 'changePassword',
            'completed': 'redirect',
            'denied': 'redirect',
            'expired': 'redirect',
        }[status]

    @staticmethod
    def _page_projection(
        record: Mapping[str, Any],
        ttl: int,
        client: 'SysOAuthClient',
        scopes: Mapping[str, 'SysOAuthScope'],
    ) -> dict[str, Any]:
        """
        构建不含协议内部绑定和 CSRF 摘要的页面投影

        :param record: 交互记录
        :param ttl: 剩余有效期秒数
        :param client: 当前启用的应用
        :param scopes: 当前应用允许的启用权限定义
        :return: 交互页面数据
        """

        next_action = InteractionService._next_action(record['status'])

        return {
            'interactionId': record['interactionId'],
            'client': {
                'clientId': client.client_id,
                'clientName': client.client_name,
                'logoUri': client.logo_uri,
                'policyUri': client.policy_uri,
                'tosUri': client.tos_uri,
            },
            'requestedScopes': [
                {
                    'scope': scope,
                    'name': scopes[scope].scope_name,
                    'description': _PUBLIC_SCOPE_DESCRIPTIONS.get(scope),
                    'sensitive': bool(scopes[scope].sensitive),
                    'required': scope == 'openid' or not bool(scopes[scope].consent_required),
                }
                for scope in record['scopes']
            ],
            'nextAction': next_action,
            'captchaEnabled': False,
            'expiresIn': max(0, int(ttl)),
        }


@dataclass(frozen=True)
class CaptchaOutcome:
    """
    验证码业务结果；HTTP 状态和响应头由 Controller 决定
    """

    result: CaptchaResponseModel | None = None
    rate_limited: bool = False
    retry_after: int | None = None
    unavailable: bool = False


class InteractionFlowService:
    """
    交互状态模块服务层
    """

    @staticmethod
    async def commit_transition(
        db: AsyncSession,
        coordinator: AfterCommitCoordinator,
        redis: Redis,
        interaction_id: str,
        target: str,
        updates: dict[str, Any] | None = None,
        compensate: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        提交数据库事务并推进交互状态

        :param db: 异步数据库会话
        :param coordinator: 提交后副作用协调器
        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :param target: 交互状态目标值
        :param updates: 状态更新字段
        :param compensate: 失败时执行的补偿回调
        :return: None
        """

        initial = await InteractionService.get_record(redis, interaction_id)
        expected_status = initial['status']
        expected_version = initial['version']
        transition_errors: list[Exception] = []

        async def transition() -> None:
            """
            推进交互状态

            :return: 状态转换结果
            """

            try:
                await InteractionService.transition(
                    redis, interaction_id, {expected_status}, target, updates, expected_version=expected_version
                )
            except Exception as exc:
                transition_errors.append(exc)
                raise

        await coordinator.register(transition)
        try:
            await coordinator.commit(db)
        except Exception:
            await db.rollback()
            raise
        if transition_errors:
            if compensate is not None:
                try:
                    await compensate()
                except Exception:
                    pass
            raise OidcInteractionException(
                interaction_id, 'Interaction transition failed', error='server_error', status_code=500
            )
        if coordinator.callback_errors:
            raise OidcInteractionException(
                interaction_id, 'Interaction cache callback failed', error='server_error', status_code=500
            )

    @staticmethod
    async def csrf_record(redis: Redis, interaction_id: str, csrf_token: str | None) -> dict[str, Any]:
        """
        校验 CSRF 并返回交互记录

        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :param csrf_token: CSRF Token
        :return: 已校验的交互记录
        """

        record = await InteractionService.get_record(redis, interaction_id)
        if not InteractionService.verify_csrf(record, csrf_token or '', pepper=OidcConfig.oidc_token_hash_pepper):
            raise OidcInteractionException(
                interaction_id, 'CSRF validation failed', error='invalid_request', status_code=403
            )
        return record

    @staticmethod
    def require_status(record: dict[str, Any], expected: str) -> None:
        """
        校验业务前置条件

        :param record: 交互记录
        :param expected: 期望的状态
        :return: None
        """

        if record.get('status') != expected:
            raise OidcInteractionException(
                record.get('interactionId'), 'Interaction state has changed', error='invalid_request', status_code=409
            )

    @staticmethod
    async def captcha(redis: Redis, interaction_id: str, client_ip: str | None) -> CaptchaOutcome:
        """
        生成交互验证码响应

        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :param client_ip: 客户端 IP 地址
        :return: 验证码响应结果
        """

        try:
            await OidcRateLimiter.enforce(
                redis,
                OidcRedisKey.interaction_captcha_rate_limit(
                    OidcRedisKey.hash_sensitive_identifier(
                        f'{interaction_id}:{client_ip or ""}',
                        OidcConfig.oidc_token_hash_pepper,
                    )
                ),
                limit=5,
                window_seconds=60,
            )
        except RateLimitExceeded as exc:
            return CaptchaOutcome(rate_limited=True, retry_after=exc.retry_after)
        except RateLimitUnavailable:
            return CaptchaOutcome(unavailable=True)
        await InteractionService.get_record(redis, interaction_id)
        enabled = await InteractionFlowService.captcha_enabled(redis)
        if enabled:
            image, answer = await CaptchaService.create_captcha_image_service()
            captcha_id = str(uuid4())
            await redis.set(f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{captcha_id}', answer, ex=timedelta(minutes=2))
            result = CaptchaResponseModel(captcha_enabled=True, uuid=captcha_id, img=image)
        else:
            result = CaptchaResponseModel(captcha_enabled=False)
        return CaptchaOutcome(result=result)

    @staticmethod
    async def captcha_enabled(redis: Redis) -> bool:
        """
        读取交互验证码开关

        :param redis: Redis 客户端
        :return: 是否启用验证码
        """

        value = await redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.captchaEnabled')

        return value in {'true', b'true', True}

    @staticmethod
    async def reserve_completion(redis: Redis, interaction_id: str) -> str | None:
        """
        保留交互完成标记 Key

        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :return: 完成标记 Key 或 None
        """

        ttl = await redis.ttl(OidcRedisKey.interaction(interaction_id))
        if not isinstance(ttl, int) or ttl <= 0:
            return None
        marker = OidcRedisKey.interaction(f'{interaction_id}-completion')
        reserved = await redis.set(marker, 'reserved', ex=ttl, nx=True)

        return marker if reserved else None

    @staticmethod
    def interaction_result(interaction_id: str, next_action: str) -> InteractionResultModel:
        """
        构建交互结果响应

        :param interaction_id: 交互流程标识
        :param next_action: 下一步交互动作
        :return: 交互响应
        """

        return InteractionResultModel(
            next_action=next_action,
            interaction_id=interaction_id,
            redirect_url=f'/auth/interaction/{interaction_id}/complete' if next_action == 'redirect' else None,
        )

    @staticmethod
    async def best_effort_delete(redis: Redis, key: str) -> None:
        """
        尽力删除 Redis Key 并吞掉删除异常

        :param redis: Redis 客户端
        :param key: Redis Key
        :return: None
        """

        try:
            await redis.delete(key)
        except Exception:
            pass

    @staticmethod
    async def rollback(db: AsyncSession) -> None:
        """
        回滚数据库事务

        :param db: 异步数据库会话
        :return: None
        """

        try:
            await db.rollback()
        except Exception:
            pass


@dataclass(frozen=True)
class InteractionLoginOutcome:
    """
    登录/改密业务结果；Cookie 和 JSON 响应由 Controller 写出
    """

    result: InteractionResultModel | None = None
    cookie: str | None = None
    failure_message: str | None = None


class InteractionLoginService:
    """
    交互登录模块服务层
    """

    @staticmethod
    def credential_proof(interaction_id: str, user_id: int, subject_id: str, auth_version: int) -> str:
        """
        构建凭据证明摘要

        :param interaction_id: 交互流程标识
        :param user_id: 本地用户 ID
        :param subject_id: 稳定身份主体 ID
        :param auth_version: 认证版本
        :return: 凭据证明摘要
        """

        return hmac.new(
            OidcConfig.oidc_token_hash_pepper.encode(),
            f'{interaction_id}:{user_id}:{subject_id}:{auth_version}'.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def login(
        redis: Redis,
        interaction_id: str,
        body: InteractionLoginModel,
        db: AsyncSession,
        csrf_token: str | None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> InteractionLoginOutcome:
        """
        校验本地凭据并推进认证交互

        :param redis: 交互 Redis
        :param interaction_id: Interaction 标识
        :param body: 登录凭据和验证码参数
        :param db: 异步数据库会话
        :param csrf_token: Interaction CSRF 原文
        :param client_ip: 客户端 IP 地址
        :param user_agent: 客户端 User-Agent
        :return: 下一步交互动作
        """

        record = await InteractionFlowService.csrf_record(redis, interaction_id, csrf_token)
        InteractionFlowService.require_status(record, 'awaiting_login')
        try:
            result = await CredentialAuthenticationService.authenticate_oidc(
                redis,
                db,
                client_ip=client_ip,
                user_name=body.user_name,
                password=body.password,
                code=body.code,
                uuid=body.uuid,
                captcha_enabled=await InteractionFlowService.captcha_enabled(redis),
                remember_me=body.remember_me,
            )
        except CredentialAuthenticationError:
            await AuditService.record_interaction_failure(
                db,
                OidcAuditEvent.LOGIN_FAILED,
                client_id=record.get('clientId'),
                failure_code='invalid_credentials',
            )
            return InteractionLoginOutcome(failure_message='登录失败')

        subject = await IdentitySubjectService.require_by_user_id(
            db, result.user.user_id, audit_writer=AuditService.interaction_subject_writer(db)
        )
        coordinator = AfterCommitCoordinator()
        cookie: str | None = None
        session: SysSsoSession | None = None
        target_status = (
            'password_change_required'
            if result.password_change_required
            else 'awaiting_consent'
            if bool(record.get('consentRequired'))
            else 'completed'
        )
        updates: dict[str, Any] = {
            'authenticatedSid': None,
            'userId': result.user.user_id,
            'subjectId': subject.subject_id,
            'authVersion': subject.auth_version,
        }
        if result.password_change_required:
            updates['credentialProofHash'] = InteractionLoginService.credential_proof(
                record['interactionId'], result.user.user_id, subject.subject_id, subject.auth_version
            )
        else:
            cookie, session = await SsoSessionService.create(
                db,
                redis,
                result.user.user_id,
                subject.subject_id,
                subject.auth_version,
                result.acr,
                result.amr,
                ip_address=client_ip,
                user_agent=user_agent,
                remember_me=result.remember_me,
                pepper=OidcConfig.oidc_token_hash_pepper,
                coordinator=coordinator,
            )
            updates['authenticatedSid'] = session.sid
        await AuditService.record(
            db,
            OidcAuditEvent.LOGIN_SUCCEEDED,
            'success',
            client_id=record.get('clientId'),
            user_id=result.user.user_id,
            subject_id=str(subject.subject_id),
            sid=session.sid if session is not None else None,
        )

        async def compensate() -> None:
            """
            执行事务补偿

            :return: None
            """

            if session is None:
                return
            await InteractionFlowService.best_effort_delete(redis, OidcRedisKey.interaction(interaction_id))
            try:
                cleanup = AfterCommitCoordinator()
                await SsoSessionService.revoke(
                    db, redis, session.sid, reason='interaction_transition_failed', coordinator=cleanup
                )
                await cleanup.commit(db)
            except Exception:
                pass
            try:
                await AuditService.record_independent(
                    db,
                    OidcAuditEvent.LOGIN_FAILED,
                    'failure',
                    risk_level='high',
                    client_id=record.get('clientId'),
                    user_id=result.user.user_id,
                    failure_code='interaction_transition_failed',
                )
            except Exception:
                pass

        await InteractionFlowService.commit_transition(
            db, coordinator, redis, interaction_id, target_status, updates, compensate=compensate
        )
        next_action = (
            'changePassword'
            if target_status == 'password_change_required'
            else ('consent' if target_status == 'awaiting_consent' else 'redirect')
        )
        model = InteractionResultModel(
            next_action=next_action,
            interaction_id=interaction_id,
            redirect_url=f'/auth/interaction/{interaction_id}/complete' if target_status == 'completed' else None,
            reason=result.password_change_reason if target_status == 'password_change_required' else None,
        )

        return InteractionLoginOutcome(result=model, cookie=cookie)

    @staticmethod
    async def change_password(
        redis: Redis,
        interaction_id: str,
        body: ChangePasswordModel,
        db: AsyncSession,
        csrf_token: str | None,
    ) -> InteractionLoginOutcome:
        """
        修改初始或过期密码并重新建立当前 SSO Session

        :param redis: 交互 Redis
        :param interaction_id: Interaction 标识
        :param body: 原密码、新密码和确认密码
        :param db: 异步数据库会话
        :param csrf_token: Interaction CSRF 原文
        :return: 下一步交互动作
        """

        record = await InteractionFlowService.csrf_record(redis, interaction_id, csrf_token)
        InteractionFlowService.require_status(record, 'password_change_required')
        user = await IdentityUserDao.get_active_user(db, int(record.get('userId') or 0))
        proof = InteractionLoginService.credential_proof(
            record['interactionId'],
            int(record.get('userId') or 0),
            str(record.get('subjectId') or ''),
            int(record.get('authVersion') or 0),
        )
        if (
            user is None
            or user.status != '0'
            or user.del_flag != '0'
            or not PwdUtil.verify_password(body.old_password, user.password)
            or not hmac.compare_digest(str(record.get('credentialProofHash') or ''), proof)
        ):
            await AuditService.record_interaction_failure(
                db,
                OidcAuditEvent.LOGIN_FAILED,
                client_id=record.get('clientId'),
                user_id=record.get('userId'),
                failure_code='password_change_failed',
            )
            return InteractionLoginOutcome(failure_message='改密失败')
        if PwdUtil.verify_password(body.new_password, user.password):
            await AuditService.record_interaction_failure(
                db,
                OidcAuditEvent.LOGIN_FAILED,
                client_id=record.get('clientId'),
                user_id=record.get('userId'),
                failure_code='password_reuse',
            )
            return InteractionLoginOutcome(failure_message='新密码不能与旧密码相同')

        try:
            await UserService.validate_password_services(redis, body.new_password)
            user.password = PwdUtil.get_password_hash(body.new_password)
            user.pwd_update_date = TimezoneUtil.utc_now()
            await IdentitySubjectService.require_by_user_id(
                db, user.user_id, audit_writer=AuditService.interaction_subject_writer(db)
            )
            coordinator = AfterCommitCoordinator()
            await SsoSessionService.revoke_user(
                db, redis, user.user_id, reason='password_changed', coordinator=coordinator
            )
            await IdentitySecurityEventService.handle_user_event(
                db, user.user_id, 'password_changed', now=TimezoneUtil.utc_now()
            )
            subject = await IdentitySubjectService.require_by_user_id(
                db, user.user_id, audit_writer=AuditService.interaction_subject_writer(db)
            )
            cookie, session = await SsoSessionService.create(
                db,
                redis,
                user.user_id,
                subject.subject_id,
                subject.auth_version,
                'urn:ruoyi:acr:pwd',
                ('pwd',),
                pepper=OidcConfig.oidc_token_hash_pepper,
                coordinator=coordinator,
            )
            target_status = 'awaiting_consent' if bool(record.get('consentRequired')) else 'completed'
            await AuditService.record(
                db,
                OidcAuditEvent.LOGIN_SUCCEEDED,
                'success',
                client_id=record.get('clientId'),
                user_id=user.user_id,
                subject_id=str(subject.subject_id),
                sid=session.sid,
            )

            async def compensate() -> None:
                """
                执行事务补偿

                :return: None
                """

                await InteractionFlowService.best_effort_delete(redis, OidcRedisKey.interaction(interaction_id))
                try:
                    cleanup = AfterCommitCoordinator()
                    await SsoSessionService.revoke(
                        db, redis, session.sid, reason='interaction_transition_failed', coordinator=cleanup
                    )
                    await cleanup.commit(db)
                except Exception:
                    pass
                try:
                    await AuditService.record_independent(
                        db,
                        OidcAuditEvent.LOGIN_FAILED,
                        'failure',
                        risk_level='high',
                        client_id=record.get('clientId'),
                        user_id=user.user_id,
                        failure_code='password_change_saga_failed',
                    )
                except Exception:
                    pass

            await InteractionFlowService.commit_transition(
                db,
                coordinator,
                redis,
                interaction_id,
                target_status,
                {
                    'authenticatedSid': session.sid,
                    'userId': user.user_id,
                    'subjectId': subject.subject_id,
                    'authVersion': subject.auth_version,
                },
                compensate=compensate,
            )
        except (OAuthProtocolException, ServiceException, SsoSessionError, IdentitySecurityEventError):
            await AuditService.record_interaction_failure(
                db,
                OidcAuditEvent.LOGIN_FAILED,
                client_id=record.get('clientId'),
                user_id=record.get('userId'),
                failure_code='password_change_failed',
            )
            return InteractionLoginOutcome(failure_message='改密失败')
        model = InteractionResultModel(
            next_action='consent' if target_status == 'awaiting_consent' else 'redirect',
            interaction_id=interaction_id,
            redirect_url=f'/auth/interaction/{interaction_id}/complete' if target_status == 'completed' else None,
        )

        return InteractionLoginOutcome(result=model, cookie=cookie)
