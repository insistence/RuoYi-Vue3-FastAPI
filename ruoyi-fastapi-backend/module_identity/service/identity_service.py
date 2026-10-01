from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy.exc import IntegrityError

from common.constant import CommonConstant, OidcAuditEvent
from common.enums import RedisInitKeyConfig
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_admin.dao.login_dao import login_by_account
from module_identity.dao.identity_subject_dao import IdentitySubjectDao
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.audit_service import AuditService
from utils.oidc_util import OidcUtil
from utils.pwd_util import PwdUtil
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy import Row
    from sqlalchemy.ext.asyncio import AsyncSession

    from module_admin.entity.do.dept_do import SysDept
    from module_admin.entity.do.user_do import SysUser
    from module_admin.entity.vo.login_vo import UserLogin
    from module_identity.entity.do.identity_subject_do import SysIdentitySubject

_DUMMY_PASSWORD_HASH = '$2b$12$ySHJfAWxzh49cIc7M5L21e5GlPyA7QhE2GkLn9XuUTqmKIRqhWIja'
_LOGIN_FAILURE_TTL = timedelta(minutes=10)
_CAPTCHA_CONSUME_SCRIPT = """
local value = redis.call('get', KEYS[1])
if value then
    redis.call('del', KEYS[1])
end
return value
"""
_OIDC_FAILURE_SCRIPT = """
if redis.call('exists', KEYS[2]) == 1 then
    return -1
end
local count = redis.call('incr', KEYS[1])
if count == 1 then
    redis.call('expire', KEYS[1], ARGV[2])
end
if count > tonumber(ARGV[1]) then
    redis.call('del', KEYS[1])
    redis.call('set', KEYS[2], '1', 'EX', ARGV[2])
    return -1
end
return count
"""


CredentialReason = Literal[
    'invalid_credentials',
    'ip_blocked',
    'captcha_missing',
    'captcha_invalid',
    'account_locked',
    'user_disabled',
]


@dataclass(frozen=True)
class CredentialAuthenticationResult:
    """
    凭据校验成功后的稳定结果，不包含任何 Token

    :param user: 已通过密码检查的本地用户对象
    :param dept: 用户所属的部门对象或 None
    :param acr: 密码认证上下文引用
    :param amr: 实际使用的认证方法集合
    :param remember_me: 后续 SSO 服务处理的记住登录选择
    :param password_change_required: 是否必须修改初始或过期密码
    :param password_change_reason: 修改密码原因
    """

    user: SysUser
    dept: SysDept | None
    acr: str
    amr: tuple[str, ...]
    remember_me: bool
    password_change_required: bool
    password_change_reason: str | None


class CredentialAuthenticationError(Exception):
    """
    凭据校验失败的内部分类异常

    :param reason: 脱敏后的失败原因分类
    :param legacy_message: Legacy 登录必须保持的中文错误消息
    """

    def __init__(self, reason: CredentialReason, legacy_message: str) -> None:
        """
        初始化对象状态

        :param reason: 凭据校验失败原因
        :param legacy_message: Legacy 登录错误消息
        :return: None
        """

        self.reason = reason
        self.legacy_message = legacy_message
        super().__init__(legacy_message)


class CredentialAuthenticationService:
    """
    凭据认证模块服务层
    """

    ACR_PASSWORD = 'urn:ruoyi:acr:pwd'

    @classmethod
    async def authenticate_legacy(
        cls,
        redis: Redis,
        query_db: AsyncSession,
        login_user: UserLogin,
        *,
        client_ip: str | None,
        skip_captcha: bool = False,
    ) -> Row[tuple[SysUser, SysDept]]:
        """
        执行 Legacy 登录的原有凭据检查，不签发 JWT

        :param redis: Legacy 登录使用的 Redis 客户端
        :param query_db: 异步数据库会话
        :param login_user: Legacy 登录参数
        :param client_ip: Controller 请求解析得到的客户端 IP
        :param skip_captcha: 开发环境 API 文档登录是否跳过验证码
        :return: 通过检查的用户和部门行
        :raises CredentialAuthenticationError: 使用 Legacy 中文语义分类失败
        """

        await cls._check_ip(client_ip, redis)
        user_name = login_user.user_name
        lock_key = f'{RedisInitKeyConfig.ACCOUNT_LOCK.key}:{user_name}'
        account_lock = await redis.get(lock_key)
        if user_name == account_lock:
            raise CredentialAuthenticationError('account_locked', '账号已锁定，请稍后再试')

        if login_user.captcha_enabled and not skip_captcha:
            await cls._check_legacy_captcha(redis, login_user)

        user = await login_by_account(query_db, user_name)
        if not user:
            raise CredentialAuthenticationError('invalid_credentials', '用户不存在')
        if not cls._verify(login_user.password, user[0].password):
            await cls._record_legacy_password_error(redis, user_name)
        if user[0].status == '1':
            raise CredentialAuthenticationError('user_disabled', '用户已停用')
        await redis.delete(f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{user_name}')

        return user

    @classmethod
    async def authenticate_oidc(
        cls,
        redis: Redis,
        query_db: AsyncSession,
        *,
        client_ip: str | None = None,
        user_name: str,
        password: str,
        code: str | None = None,
        uuid: str | None = None,
        captcha_enabled: bool = False,
        remember_me: bool = False,
    ) -> CredentialAuthenticationResult:
        """
        执行 OIDC 交互的本地凭据校验，不触发 Legacy Token 流程

        用户不存在和密码错误共享 ``invalid_credentials`` 分类；用户名只用于
        HMAC 计算，OIDC 错误计数与锁定键不会包含用户名原文

        :param redis: OIDC 交互使用的 Redis 客户端
        :param client_ip: Controller 请求解析得到的客户端 IP
        :param query_db: 异步数据库会话
        :param user_name: 用户名，仅在内存中参与查询和摘要
        :param password: 用户密码，不写入日志或 Redis
        :param code: 可选一次性验证码
        :param uuid: 验证码 Redis 标识
        :param captcha_enabled: 是否要求验证码
        :param remember_me: 交由后续 SSO 服务处理的记住登录选项
        :return: 凭据成功结果，不含 Token
        :raises CredentialAuthenticationError: 脱敏分类的凭据失败
        """

        await cls._check_ip(client_ip, redis)
        username_digest = OidcUtil.hash_sensitive_identifier(user_name, OidcConfig.oidc_token_hash_pepper)
        failure_key = OidcRedisKey.login_user_rate_limit(username_digest)
        lock_key = f'{failure_key}:lock'
        if await redis.get(lock_key):
            raise CredentialAuthenticationError('account_locked', '账号已锁定，请稍后再试')
        if captcha_enabled:
            await cls._check_oidc_captcha(redis, code, uuid)

        user_row = await login_by_account(query_db, user_name)
        stored_hash = user_row[0].password if user_row else _DUMMY_PASSWORD_HASH
        password_valid = cls._verify(password, stored_hash)
        if user_row is None or not password_valid:
            await cls._record_oidc_password_error(redis, failure_key, lock_key)
            raise CredentialAuthenticationError('invalid_credentials', '账号或密码错误')
        if user_row[0].status == '1':
            raise CredentialAuthenticationError('user_disabled', '用户已停用')

        await redis.delete(failure_key)
        await redis.delete(lock_key)
        password_change_required, change_reason = await cls._password_policy(redis, user_row[0])
        methods = ('pwd', 'captcha') if captcha_enabled else ('pwd',)

        return CredentialAuthenticationResult(
            user=user_row[0],
            dept=user_row[1],
            acr=cls.ACR_PASSWORD,
            amr=methods,
            remember_me=remember_me,
            password_change_required=password_change_required,
            password_change_reason=change_reason,
        )

    @staticmethod
    def _verify(password: str, stored_hash: str | None) -> bool:
        """
        使用项目 PwdUtil 验证密码，异常哈希按失败处理

        :param password: 用户密码
        :param stored_hash: 已存储的密码摘要
        :return: 密码是否匹配
        """

        try:
            return bool(PwdUtil.verify_password(password, stored_hash or _DUMMY_PASSWORD_HASH))
        except (TypeError, ValueError):
            return False

    @classmethod
    async def _check_ip(cls, client_ip: str | None, redis: Redis) -> None:
        """
        拒绝系统配置黑名单中的客户端 IP

        :param client_ip: 客户端 IP 地址
        :param redis: Redis 客户端
        :return: None
        """

        value = await redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.login.blackIPList')
        if client_ip in (value.split(',') if value else []):
            raise CredentialAuthenticationError('ip_blocked', '当前IP禁止登录')

    @classmethod
    async def _check_legacy_captcha(cls, redis: Redis, login_user: UserLogin) -> None:
        """
        按原有非消费语义校验 Legacy 验证码

        :param redis: Redis 客户端
        :param login_user: Legacy 登录请求
        :return: None
        """

        value = await redis.get(f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{login_user.uuid}')
        if not value:
            raise CredentialAuthenticationError('captcha_missing', '验证码已失效')
        if login_user.code != str(value):
            raise CredentialAuthenticationError('captcha_invalid', '验证码错误')

    @classmethod
    async def _check_oidc_captcha(cls, redis: Redis, code: str | None, uuid: str | None) -> None:
        """
        原子消费 OIDC 验证码，阻止验证码重放

        :param redis: Redis 客户端
        :param code: OIDC 验证码
        :param uuid: 验证码标识
        :return: None
        """

        if not uuid:
            raise CredentialAuthenticationError('captcha_missing', '验证码已失效或不存在')
        key = f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{uuid}'
        value = await redis.eval(_CAPTCHA_CONSUME_SCRIPT, 1, key)
        if not value:
            raise CredentialAuthenticationError('captcha_missing', '验证码已失效或不存在')
        expected = value.decode('utf-8') if isinstance(value, bytes) else str(value)
        if code != expected:
            raise CredentialAuthenticationError('captcha_invalid', '验证码错误')

    @classmethod
    async def _record_legacy_password_error(cls, redis: Redis, user_name: str) -> None:
        """
        保持 Legacy 错误计数、阈值和十分钟 TTL 完全不变

        :param redis: Redis 客户端
        :param user_name: 用户名
        :return: None
        """

        key = f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{user_name}'
        cached = await redis.get(key)
        count = int(cached or 0) + 1
        await redis.set(key, count, ex=_LOGIN_FAILURE_TTL)
        if count > CommonConstant.PASSWORD_ERROR_COUNT:
            await redis.delete(key)
            await redis.set(f'{RedisInitKeyConfig.ACCOUNT_LOCK.key}:{user_name}', user_name, ex=_LOGIN_FAILURE_TTL)
            raise CredentialAuthenticationError(
                'account_locked', '10分钟内密码已输错超过5次，账号已锁定，请10分钟后再试'
            )
        raise CredentialAuthenticationError('invalid_credentials', '密码错误')

    @classmethod
    async def _record_oidc_password_error(cls, redis: Redis, failure_key: str, lock_key: str) -> None:
        """
        记录 OIDC 摘要命名空间错误状态，不写入用户名

        :param redis: Redis 客户端
        :param failure_key: OIDC 失败计数 Key
        :param lock_key: OIDC 锁定 Key
        :return: None
        """

        result = await redis.eval(
            _OIDC_FAILURE_SCRIPT,
            2,
            failure_key,
            lock_key,
            str(CommonConstant.PASSWORD_ERROR_COUNT),
            str(int(_LOGIN_FAILURE_TTL.total_seconds())),
        )
        if int(result or 0) < 0:
            raise CredentialAuthenticationError('account_locked', '账号已锁定，请稍后再试')

    @classmethod
    async def _password_policy(cls, redis: Redis, user: SysUser) -> tuple[bool, str | None]:
        """
        复用系统初始密码和密码有效期配置，处理 naive/aware 时间

        :param redis: Redis 客户端
        :param user: 系统用户对象
        :return: 密码修改要求及原因
        """

        init_modify = await redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.initPasswordModify')
        update_time = getattr(user, 'pwd_update_date', None)
        if init_modify == '1' and update_time is None:
            return True, 'initial_password'
        days_value = await redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.passwordValidateDays')
        try:
            days = int(days_value or 0)
        except (TypeError, ValueError):
            days = 0
        if days > 0:
            if update_time is None:
                return True, 'password_expired'
            now = TimezoneUtil.utc_now()
            update_time = TimezoneUtil.to_utc(update_time)
            if now > update_time + timedelta(days=days):
                return True, 'password_expired'
        return False, None


class ClaimService:
    """
    OIDC Claim 模块服务层
    """

    SCOPE_CLAIMS = {
        'openid': frozenset({'sub'}),
        'profile': frozenset({'name', 'preferred_username', 'picture', 'updated_at'}),
        'email': frozenset({'email', 'email_verified'}),
        'phone': frozenset({'phone_number', 'phone_number_verified'}),
        'roles': frozenset({'roles'}),
        'role': frozenset({'roles'}),
        'dept': frozenset({'dept_id', 'dept_name'}),
        'department': frozenset({'dept_id', 'dept_name'}),
    }
    FORBIDDEN_CLAIMS = frozenset(
        {
            'user_id',
            'userid',
            'password',
            'passwd',
            'secret',
            'token',
            'access_token',
            'refresh_token',
            'client_secret',
        }
    )

    @classmethod
    def _claim_set(cls, value: Any) -> set[str]:
        """
        规范化策略或白名单中的 Claim 名称

        :param value: 待规范化的 Claim 名称集合
        :return: 规范化 Claim 集合
        """

        if value is True:
            return set(cls.SCOPE_CLAIMS['openid'] | cls.SCOPE_CLAIMS['profile'])
        if isinstance(value, str):
            return OidcUtil.scope_set(value)
        if isinstance(value, Mapping):
            value = value.get('claims', value.get('allowed_claims', []))
        if isinstance(value, Iterable) and not isinstance(value, (bytes, str, Mapping)):
            return {item for item in value if isinstance(item, str)}
        return set()

    @classmethod
    def _client_claims_for_scope(cls, scope: str, policy: Any) -> set[str]:
        """
        取得 Client 对某一 Scope 的 Claim 策略

        :param scope: 待读取策略的 Scope 名称
        :param policy: Scope Claim 策略
        :return: Scope 对应 Claim 集合
        """

        if isinstance(policy, Mapping):
            if scope in policy:
                value = policy[scope]
                return set(cls.SCOPE_CLAIMS.get(scope, ())) if value is True else cls._claim_set(value)
            scopes = policy.get('scopes')
            if scopes is not None and scope not in OidcUtil.scope_set(scopes):
                return set()
            if scopes is not None:
                return set(cls.SCOPE_CLAIMS.get(scope, ()))
            return set()
        allowed_scopes = OidcUtil.scope_set(policy)

        return set(cls.SCOPE_CLAIMS.get(scope, ())) if scope in allowed_scopes else set()

    @classmethod
    def effective_claims(
        cls,
        requested_scopes: str | Iterable[str] | None,
        client_scope_policy: Any,
        resource_allowed_claims: Any,
    ) -> set[str]:
        """
        计算请求 Scope、Client 策略和 Resource 白名单的三重交集

        :param requested_scopes: 请求的空格分隔 Scope 或 Scope 集合
        :param client_scope_policy: Client 的 Scope 到 Claim 策略映射
        :param resource_allowed_claims: Resource 允许的 Claim 列表
        :return: 可安全生成的 Claim 名称集合
        """

        requested = OidcUtil.scope_set(requested_scopes)
        client_claims = set().union(*(cls._client_claims_for_scope(scope, client_scope_policy) for scope in requested))
        resource_claims = cls._claim_set(resource_allowed_claims)

        return (client_claims & resource_claims) - cls.FORBIDDEN_CLAIMS

    @classmethod
    def _safe_values(cls, user: Any, subject_id: str | None, roles: Any, department: Any) -> dict[str, Any]:
        """
        抽取允许的用户属性，明确排除本地 ID 和密码

        :param user: SysUser ORM 记录或用户 Claim 字段映射
        :param subject_id: 稳定身份主体 ID
        :param roles: 角色集合
        :param department: 部门对象或部门映射
        :return: 安全 Claim 字段映射
        """

        values = {
            'sub': subject_id or OidcUtil.read_field(user, 'subject_id'),
            'name': OidcUtil.read_field(user, 'name', OidcUtil.read_field(user, 'nick_name')),
            'preferred_username': OidcUtil.read_field(
                user, 'preferred_username', OidcUtil.read_field(user, 'user_name')
            ),
            'picture': OidcUtil.read_field(user, 'picture', OidcUtil.read_field(user, 'avatar')),
            'updated_at': OidcUtil.claim_numeric_date(
                OidcUtil.read_field(user, 'updated_at', OidcUtil.read_field(user, 'update_time'))
            ),
            'email': OidcUtil.read_field(user, 'email'),
            'email_verified': OidcUtil.read_field(user, 'email_verified'),
            'phone_number': OidcUtil.read_field(user, 'phone_number', OidcUtil.read_field(user, 'phonenumber')),
            'phone_number_verified': OidcUtil.read_field(user, 'phone_number_verified'),
            'roles': roles if roles is not None else OidcUtil.read_field(user, 'roles'),
        }
        dept = department if department is not None else OidcUtil.read_field(user, 'dept')
        if dept is None:
            dept = {
                'dept_id': OidcUtil.read_field(user, 'dept_id'),
                'dept_name': OidcUtil.read_field(user, 'dept_name'),
            }
        if isinstance(dept, Mapping):
            values['dept_id'] = dept.get('dept_id')
            values['dept_name'] = dept.get('dept_name')
        else:
            values['dept_id'] = getattr(dept, 'dept_id', None)
            values['dept_name'] = getattr(dept, 'dept_name', None)
        return values

    @classmethod
    def build_claims(
        cls,
        user: Any,
        requested_scopes: str | Iterable[str] | None,
        client_scope_policy: Any,
        resource_allowed_claims: Any,
        *,
        subject_id: str | None = None,
        roles: Any = None,
        department: Any = None,
    ) -> dict[str, Any]:
        """
        为用户构建经过三重授权和敏感字段过滤的 OIDC Claims

        :param user: 已加载的用户 ORM 对象或安全字段映射
        :param requested_scopes: 请求 Scope
        :param client_scope_policy: Client Scope 到 Claim 的授权策略
        :param resource_allowed_claims: Resource Claim 白名单
        :param subject_id: 稳定 OIDC Subject，不能使用本地 user_id 替代
        :param roles: 已按项目角色 DAO 查询的角色 key 集合
        :param department: 已按项目部门 DAO 查询的部门对象或映射
        :return: 最小 OIDC Claim 映射
        """

        requested = OidcUtil.scope_set(requested_scopes)
        allowed = cls.effective_claims(requested, client_scope_policy, resource_allowed_claims)
        stable_subject = subject_id or OidcUtil.read_field(user, 'subject_id')
        if 'openid' in requested:
            if not isinstance(stable_subject, str) or not stable_subject.strip():
                raise OAuthProtocolException('server_error', 'User identity mapping is unavailable', 500)
            if 'sub' not in allowed:
                raise OAuthProtocolException('invalid_scope', 'OpenID scope requires the sub claim', 400)
        values = cls._safe_values(user, subject_id, roles, department)
        role_keys: set[str] = set()
        if isinstance(client_scope_policy, Mapping):
            for scope in requested:
                rule = client_scope_policy.get(scope)
                if isinstance(rule, Mapping) and isinstance(rule.get('allowed_role_keys'), list):
                    role_keys.update(
                        key for key in rule['allowed_role_keys'] if isinstance(key, str) and '*' not in key
                    )
        if 'roles' in values:
            values['roles'] = [role for role in values['roles'] if role in role_keys]
        return {
            key: value
            for key, value in values.items()
            if key in allowed and key not in cls.FORBIDDEN_CLAIMS and value is not None
        }

    @classmethod
    async def load_roles_and_department(cls, db: AsyncSession, user_id: int) -> tuple[list[str], SysDept | None]:
        """
        按现有 ORM DAO 使用的启用状态规则加载角色和部门

        :param db: 异步数据库会话
        :param user_id: 本地用户 ID，仅用于内部查询，不会进入 Claim
        :return: 角色名称列表和部门对象
        """

        return await IdentityUserDao.get_claim_attributes(db, user_id)

    @classmethod
    async def resolve_scope_policy(
        cls,
        db: AsyncSession,
        client_pk: int,
        scopes: Iterable[str],
        *,
        resource_allowed_claims: Iterable[str] | None = None,
    ) -> tuple[dict[str, Any], set[str]]:
        """
        解析 Client Scope 策略及最终 Claim 白名单

        :param db: 异步数据库会话
        :param client_pk: Client 内部主键
        :param scopes: 当前已授权 Scope
        :param resource_allowed_claims: 可选 Resource Claim 白名单
        :return: Scope 策略映射和可用 Claim 集合
        """

        requested = set(scopes)
        bindings = await OAuthClientDao.list_scope_bindings(db, client_pk)
        definitions = await OAuthClientDao.list_scope_definitions(db)
        by_pk = {item.scope_pk: item for item in definitions}
        policy: dict[str, Any] = {}
        allowed: set[str] = set()
        for binding in bindings:
            definition = by_pk.get(binding.scope_pk)
            if definition is None or definition.status != '0' or definition.scope_code not in requested:
                continue
            policy[definition.scope_code] = binding.claim_filter if binding.claim_filter is not None else True
            allowed.update(cls._claim_set(definition.claims))
        if resource_allowed_claims is not None:
            allowed.intersection_update(cls._claim_set(resource_allowed_claims))
        return policy, allowed


class IdentitySubjectService:
    """
    身份主体模块服务层
    """

    @classmethod
    async def require_by_user_id(
        cls,
        db: AsyncSession,
        user_id: int,
        *,
        audit_db: AsyncSession | None = None,
        audit_writer: Callable[[int], Awaitable[object]] | None = None,
    ) -> SysIdentitySubject:
        """
        获取用户的稳定 Subject，缺失时拒绝继续签发

        :param db: 与当前业务事务相同的异步数据库会话
        :param user_id: 本地用户 ID
        :param audit_db: 可选独立审计会话，避免主事务回滚时丢失完整性告警
        :param audit_writer: 可选外部审计写入器，提交边界由写入器负责
        生产签发链路必须提供其中之一；两者均省略时审计仅随当前事务 flush，
        主事务回滚会一并回滚，不能作为持久化告警
        :return: 已存在的主体关联
        :raises OAuthProtocolException: 主体关联缺失或用户标识无效时抛出
        """

        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            await cls._write_missing_audit(db, user_id, audit_db=audit_db, audit_writer=audit_writer)
            raise OAuthProtocolException('server_error', 'User identity mapping is unavailable', 500)
        subject = await IdentitySubjectDao.get_by_user_id(db, user_id)
        if subject is None:
            await cls._write_missing_audit(db, user_id, audit_db=audit_db, audit_writer=audit_writer)
            raise OAuthProtocolException('server_error', 'User identity mapping is unavailable', 500)
        return subject

    @classmethod
    async def _write_missing_audit(
        cls,
        db: AsyncSession,
        user_id: int,
        *,
        audit_db: AsyncSession | None = None,
        audit_writer: Callable[[int], Awaitable[object]] | None = None,
    ) -> None:
        """
        写入主体完整性审计；审计失败不能把缺失主体变成可签发状态

        未传入独立会话或写入器时只在调用方事务中 flush，调用方必须自行承担
        回滚丢失告警的后果；持久化安全告警应使用 ``audit_writer``

        :param db: 异步数据库会话
        :param user_id: 本地用户 ID
        :param audit_db: 独立审计数据库会话
        :param audit_writer: 外部审计写入器
        :return: None
        """

        try:
            if audit_writer is not None:
                await audit_writer(user_id)
                return
            await AuditService.record(
                audit_db or db,
                event_type=OidcAuditEvent.IDENTITY_SUBJECT_MISSING,
                result='failure',
                risk_level='high',
                user_id=user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None,
                failure_code='identity_integrity',
                detail={'reason': 'subject_missing'},
            )
        except Exception:
            # 主体完整性拒绝优先于审计写入成功，调用方仍会得到 fail-closed 结果
            return

    @classmethod
    async def create_for_new_user(
        cls,
        db: AsyncSession,
        *,
        user_id: int,
        create_by: str | None = None,
        subject_id: str | None = None,
    ) -> SysIdentitySubject:
        """
        在用户创建事务中建立稳定 Subject，不提交调用方事务

        :param db: 用户创建事务使用的异步数据库会话
        :param user_id: 已创建的本地用户 ID
        :param create_by: 主体记录创建者
        :param subject_id: 测试迁移或导入场景使用的预生成 Subject
        :return: 已存在或新建的主体关联
        :raises ValueError: 用户 ID 无效时抛出
        """

        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError('身份用户编号 identity_user_id 必须为正整数')
        return await IdentitySubjectDao.create_for_user(db, user_id, create_by, subject_id)

    @classmethod
    async def repair_missing_subject(
        cls, db: AsyncSession, user_id: int, create_by: str = 'identity-repair'
    ) -> SysIdentitySubject:
        """
        幂等修复单个用户的缺失 Subject

        :param db: 异步数据库会话
        :param user_id: 待修复的本地用户 ID
        :param create_by: 回填记录的创建者标识
        :return: 已存在或本次创建的主体关联
        :raises ValueError: 用户 ID 无效时抛出
        """

        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError('身份用户编号 identity_user_id 必须为正整数')
        try:
            return await IdentitySubjectDao.create_for_user(db, user_id, create_by=create_by)
        except IntegrityError:
            existing = await IdentitySubjectDao.get_by_user_id(db, user_id)
            if existing is not None:
                return existing
            raise

    @classmethod
    async def repair_missing_subjects(
        cls,
        db: AsyncSession,
        user_ids: Iterable[int] | None = None,
        create_by: str = 'identity-repair',
    ) -> Sequence[SysIdentitySubject]:
        """
        幂等批量修复缺失 Subject，不提交调用方事务

        :param db: 异步数据库会话
        :param user_ids: 可选用户 ID 集合；省略时检查所有未删除用户
        :param create_by: 回填记录的创建者标识
        :return: 本次调用新建的主体记录集合
        """

        if user_ids is not None:
            values = list(user_ids)
            if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in values):
                raise ValueError('身份用户编号 identity_user_id 必须为正整数')
        return await IdentitySubjectDao.backfill_for_users(
            db, await IdentitySubjectDao.list_missing_user_ids(db, user_ids), create_by
        )

    @classmethod
    async def increment_auth_version(
        cls, db: AsyncSession, user_id: int, expected_version: int | None = None
    ) -> SysIdentitySubject:
        """
        原子递增用户认证版本并返回最新主体

        :param db: 异步数据库会话
        :param user_id: 本地用户 ID
        :param expected_version: 可选的乐观锁版本
        :return: 更新后的主体关联
        :raises OAuthProtocolException: 主体不存在或版本竞争失败时抛出
        """

        if not await IdentitySubjectDao.increment_auth_version(db, user_id, expected_version):
            raise OAuthProtocolException('server_error', 'User identity version could not be updated', 500)
        subject = await IdentitySubjectDao.get_by_user_id(db, user_id)
        if subject is None:
            raise OAuthProtocolException('server_error', 'User identity mapping is unavailable', 500)
        return subject

    @classmethod
    async def get_by_subject_id(cls, db: AsyncSession, subject_id: str) -> SysIdentitySubject | None:
        """
        按稳定 Subject 查询主体关联

        :param db: 异步数据库会话
        :param subject_id: 稳定 OIDC Subject
        :return: 主体关联，不存在时返回 None
        """

        return await IdentitySubjectDao.get_by_subject_id(db, subject_id)


IdentitySecurityEvent = Literal[
    'user_disabled',
    'user_deleted',
    'password_changed',
    'role_assignment_changed',
    'department_changed',
    'role_claim_changed',
    'role_disabled',
    'role_deleted',
]


class IdentitySecurityEventError(ValueError):
    """
    身份安全事件缺少主体映射或输入不满足事务约束
    """


@dataclass(frozen=True, slots=True)
class IdentitySecurityEventResult:
    """
    一次身份安全失效操作的不可变结果
    """

    affected_users: tuple[int, ...]
    revoked_sessions: int
    revoked_refresh_tokens: int


class IdentitySecurityEventService:
    """
    身份安全事件模块服务层
    """

    _EVENTS = frozenset(
        {
            'user_disabled',
            'user_deleted',
            'password_changed',
            'role_assignment_changed',
            'department_changed',
            'role_claim_changed',
            'role_disabled',
            'role_deleted',
        }
    )
    _ALWAYS_REVOKE_SSO = frozenset({'user_disabled', 'user_deleted', 'password_changed'})
    _CLAIM_EVENTS = frozenset(
        {'role_assignment_changed', 'department_changed', 'role_claim_changed', 'role_disabled', 'role_deleted'}
    )
    _TERMINAL_REFRESH_STATUSES = frozenset({'revoked', 'expired', 'reuse_detected'})
    _MAX_BATCH_USERS = 10_000
    _MAX_SID_LENGTH = 36

    @classmethod
    async def handle_user_event(
        cls,
        db: AsyncSession,
        user_id: int,
        event: IdentitySecurityEvent,
        *,
        actor: str | None = None,
        exclude_sid: str | None = None,
        revoke_sso_on_claim_change: bool = False,
        now: datetime | None = None,
    ) -> IdentitySecurityEventResult:
        """
        处理单个用户事件，但不提交调用方事务

        :param db: 与用户或角色变更共用的数据库会话
        :param user_id: 本地用户 ID
        :param event: 设计文档定义的身份安全事件
        :param actor: 可选审计操作者
        :param exclude_sid: 修改密码时允许保留的当前交互 Session
        :param revoke_sso_on_claim_change: Claim 变化时是否立即撤销 SSO
        :param now: 可注入的 项目当前时间
        :return: 版本递增及凭据撤销数量
        """

        return await cls.handle_users_event(
            db,
            (user_id,),
            event,
            actor=actor,
            exclude_sid=exclude_sid,
            revoke_sso_on_claim_change=revoke_sso_on_claim_change,
            now=now,
        )

    @classmethod
    async def handle_users_event(
        cls,
        db: AsyncSession,
        user_ids: Iterable[int],
        event: IdentitySecurityEvent,
        *,
        actor: str | None = None,
        exclude_sid: str | None = None,
        revoke_sso_on_claim_change: bool = False,
        now: datetime | None = None,
    ) -> IdentitySecurityEventResult:
        """
        按固定锁顺序批量处理身份安全事件，不提交事务

        :param db: 异步数据库会话
        :param user_ids: 本地用户 ID 集合
        :param event: 身份安全事件
        :param actor: 审计操作者标识
        :param exclude_sid: 需要排除的 Session 标识
        :param revoke_sso_on_claim_change: Claim 变化时是否撤销 SSO
        :param now: 当前时间
        :return: 安全事件处理结果
        :raises IdentitySecurityEventError: 事件、用户或主体映射不完整
        """

        try:
            ids = OidcUtil.normalize_user_ids(user_ids, max_size=cls._MAX_BATCH_USERS)
        except ValueError as exc:
            raise IdentitySecurityEventError(str(exc)) from exc
        if event not in cls._EVENTS:
            raise IdentitySecurityEventError('身份安全事件无效')
        if exclude_sid is not None and (
            event != 'password_changed'
            or not OidcUtil.is_trimmed_identifier(exclude_sid, max_length=cls._MAX_SID_LENGTH)
        ):
            raise IdentitySecurityEventError('当前安全事件不允许指定保留会话 exclude_sid')
        if not isinstance(revoke_sso_on_claim_change, bool):
            raise IdentitySecurityEventError('身份声明变更时撤销会话的配置必须为布尔值')
        if now is not None and not isinstance(now, datetime):
            raise IdentitySecurityEventError('当前时间必须为 datetime 对象')
        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        actor_value = actor.strip()[:64] if isinstance(actor, str) and actor.strip() else 'identity-security-event'

        subjects = list(await IdentitySubjectDao.list_for_users_for_update(db, ids))
        if {row.user_id for row in subjects} != set(ids):
            raise IdentitySecurityEventError('缺少用户主体映射')
        await IdentitySubjectDao.increment_auth_versions(db, ids, actor_value, current)
        revoked_refresh_tokens = await OAuthTokenDao.revoke_for_users(db, ids, reason=event, now=current)

        revoke_sso = event in cls._ALWAYS_REVOKE_SSO or (event in cls._CLAIM_EVENTS and revoke_sso_on_claim_change)
        revoked_sessions = 0
        if revoke_sso:
            revoked_sessions = await SsoSessionDao.revoke_for_users(
                db, ids, reason=event, now=current, exclude_sid=exclude_sid
            )

        await AuditService.record(
            db,
            event_type=OidcAuditEvent.SECURITY_VERSION_CHANGED,
            result='success',
            risk_level='high',
            user_id=ids[0] if len(ids) == 1 else None,
            detail={
                'event': event,
                'actor': actor_value,
                'affected_users': len(ids),
                'revoked_sessions': revoked_sessions,
                'revoked_refresh_tokens': revoked_refresh_tokens,
            },
        )

        return IdentitySecurityEventResult(ids, revoked_sessions, revoked_refresh_tokens)

    @classmethod
    async def handle_role_event(
        cls,
        db: AsyncSession,
        role_id: int,
        event: Literal['role_claim_changed', 'role_disabled', 'role_deleted'],
        *,
        actor: str | None = None,
        revoke_sso_on_claim_change: bool = False,
        now: datetime | None = None,
    ) -> IdentitySecurityEventResult:
        """
        查询角色当前成员并批量触发身份安全失效

        :param db: 异步数据库会话
        :param role_id: 角色 ID
        :param event: 身份安全事件
        :param actor: 审计操作者标识
        :param revoke_sso_on_claim_change: Claim 变化时是否撤销 SSO
        :param now: 当前时间
        :return: 安全事件处理结果
        """

        if not isinstance(role_id, int) or isinstance(role_id, bool) or role_id <= 0:
            raise IdentitySecurityEventError('角色编号 role_id 必须为正整数')
        if event not in {'role_claim_changed', 'role_disabled', 'role_deleted'}:
            raise IdentitySecurityEventError('角色安全事件无效')
        user_ids = tuple(sorted(set(await IdentityUserDao.list_user_ids_by_role_id(db, role_id))))
        if not user_ids:
            return IdentitySecurityEventResult((), 0, 0)
        return await cls.handle_users_event(
            db,
            user_ids,
            event,
            actor=actor,
            revoke_sso_on_claim_change=revoke_sso_on_claim_change,
            now=now,
        )
