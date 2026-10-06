import asyncio
import inspect
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Literal, TypeVar

from anyio import Path as AsyncPath
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import ServiceException
from module_identity.dao.oidc_key_dao import OidcKeyDao
from module_identity.entity.do.oidc_key_do import SysOidcSigningKey
from module_identity.entity.vo.oidc_key_vo import OidcKeyRotateModel, OidcKeyViewModel
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.audit_service import AuditService
from utils.log_util import logger
from utils.oidc_util import OidcUtil
from utils.time_util import TimezoneUtil

RS256 = 'RS256'
_PUBLISHED_STATUSES = frozenset({'pending', 'active', 'retiring'})
_MIN_RSA_BITS = 2048
_MIN_ENCRYPTION_KEY_BYTES = 32
_ENCRYPTION_SALT_BYTES = 16
_ROTATION_LOCK_TTL_SECONDS = 30
_ROTATION_LOCK_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

T = TypeVar('T')


class KeyServiceError(ValueError):
    """
    表示 OIDC 签名密钥管理错误
    """


class KeyService:
    """
    OIDC 签名密钥模块服务层
    """

    CACHE_MAX_AGE = 300

    @classmethod
    def _require_enabled(cls, *, management: bool = False) -> None:
        """
        校验 OIDC 签名密钥功能是否可用

        :param management: 是否允许管理模式
        :return: None
        :raises KeyServiceError: OIDC 未启用
        """

        if not OidcConfig.oidc_enabled and not management:
            raise KeyServiceError('统一认证中心未启用')

    @staticmethod
    @asynccontextmanager
    async def _rotation_lock(redis: Any) -> AsyncGenerator[None, None]:
        """
        获取密钥轮换锁

        :param redis: 应用共享 Redis 客户端；离线数据库单元测试可传 ``None``
        :return: 异步上下文管理器
        :raises KeyServiceError: 锁已被其他实例持有
        """

        if redis is None:
            yield
            return
        token = secrets.token_urlsafe(24)
        acquired = await redis.set(
            OidcRedisKey.signing_key_rotation_lock(), token, nx=True, ex=_ROTATION_LOCK_TTL_SECONDS
        )
        if not acquired:
            raise KeyServiceError('签名密钥正在轮换，请稍后重试')
        try:
            yield
        finally:
            await redis.eval(
                _ROTATION_LOCK_RELEASE_SCRIPT,
                1,
                OidcRedisKey.signing_key_rotation_lock(),
                token,
            )

    @staticmethod
    async def _private_material_async(  # noqa: PLR0912
        record: Any,
        decrypt_private_key: Callable[[str], bytes | str | Awaitable[bytes | str]] | None,
    ) -> bytes:
        """
        异步读取私钥材料

        :param record: 数据库密钥记录
        :param decrypt_private_key: 可同步或异步的解密回调
        :return: PEM 编码私钥字节
        :raises KeyServiceError: 私钥来源不合法或无法解密
        """

        reference = getattr(record, 'private_key_ref', None)
        ciphertext = getattr(record, 'private_key_ciphertext', None)
        if bool(reference) == bool(ciphertext):
            raise KeyServiceError('必须且只能配置一个签名私钥来源')
        if ciphertext:
            if decrypt_private_key is None:
                try:
                    value = OidcUtil.decrypt_signing_private_key(
                        str(ciphertext), OidcConfig.oidc_signing_key_encryption_key.encode()
                    )
                except Exception as exc:
                    raise KeyServiceError('解密签名私钥需要有效的加密密钥') from exc
            else:
                value = decrypt_private_key(str(ciphertext))
            if inspect.isawaitable(value):
                value = await value
            if isinstance(value, str):
                value = value.encode()
            if not isinstance(value, bytes) or not value:
                raise KeyServiceError('签名私钥解密器返回的数据无效')
            return value
        if OidcConfig.oidc_signing_key_source != 'file':
            if decrypt_private_key is None:
                raise KeyServiceError('外部签名私钥引用必须配置加载器')
            value = decrypt_private_key(str(reference))
            if inspect.isawaitable(value):
                value = await value
            if isinstance(value, str):
                value = value.encode()
            if not isinstance(value, bytes) or not value:
                raise KeyServiceError('签名私钥加载器返回的数据无效')
            return value
        path_value = str(reference or OidcConfig.oidc_signing_private_key_path).strip()
        if not path_value:
            raise KeyServiceError('签名私钥文件路径不能为空')
        try:
            return await AsyncPath(path_value).read_bytes()
        except OSError as exc:
            raise KeyServiceError('无法读取签名私钥文件') from exc

    @classmethod
    def _validate_record_window(cls, record: Any, now: datetime, *, require_active: bool = True) -> None:
        """
        校验签名密钥状态、算法和时间窗口

        :param record: 数据库密钥记录
        :param now: 当前项目时间
        :param require_active: 是否要求密钥处于 active 状态
        :return: None
        :raises KeyServiceError: 记录不能用于签名
        """

        expected_status = 'active' if require_active else 'pending'
        if getattr(record, 'status', None) != expected_status:
            raise KeyServiceError(f'签名密钥状态不符合要求，预期状态为 {expected_status}')
        if getattr(record, 'alg', None) != RS256 or OidcConfig.oidc_signing_algorithm != RS256:
            raise KeyServiceError('仅支持 RS256 签名密钥')
        if not OidcUtil.is_valid_kid(getattr(record, 'kid', None)):
            raise KeyServiceError('签名密钥标识 kid 包含不允许的字符')
        start = TimezoneUtil.to_optional_utc(getattr(record, 'signing_start_at', None))
        stop = TimezoneUtil.to_optional_utc(getattr(record, 'signing_stop_at', None))
        if require_active and (start is None or start > now or (stop is not None and stop <= now)):
            raise KeyServiceError('签名密钥不在有效签发时间范围内')

    @classmethod
    async def load_private_key_async(
        cls,
        record: Any,
        *,
        now: datetime | None = None,
        decrypt_private_key: Callable[[str], bytes | str | Awaitable[bytes | str]] | None = None,
        require_active: bool = True,
        management: bool = False,
    ) -> RSAPrivateKey:
        """
        异步加载并校验签名密钥 RSA 私钥

        :param record: 数据库中的签名密钥记录
        :param now: 可注入的当前时间
        :param decrypt_private_key: 解密 ciphertext 的可注入回调
        :param require_active: 是否要求密钥处于 active 状态
        :param management: 是否允许在 OIDC 关闭时执行管理校验
        :return: 已验证且不会被序列化的 RSA 私钥
        :raises KeyServiceError: 状态、来源、格式或公私钥不匹配
        """

        cls._require_enabled(management=management)
        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        cls._validate_record_window(record, current, require_active=require_active)
        material = await cls._private_material_async(record, decrypt_private_key)
        try:
            private_key = serialization.load_pem_private_key(material, password=None)
        except (TypeError, ValueError) as exc:
            raise KeyServiceError('RSA 签名私钥无效') from exc
        if not isinstance(private_key, RSAPrivateKey):
            raise KeyServiceError('签名密钥必须为 RSA 类型')
        if private_key.key_size < _MIN_RSA_BITS:
            raise KeyServiceError('RSA 签名密钥长度不得小于 2048 位')
        derived = OidcUtil.rsa_public_jwk(private_key.public_key(), getattr(record, 'kid', ''))
        try:
            expected = OidcUtil.normalize_public_jwk(record, min_rsa_bits=_MIN_RSA_BITS)
        except ValueError as exc:
            raise KeyServiceError(str(exc)) from exc
        if derived != expected:
            raise KeyServiceError('签名私钥与公开 JWK 不匹配')
        return private_key

    @classmethod
    def load_private_key(
        cls,
        record: Any,
        *,
        now: datetime | None = None,
        require_active: bool = True,
    ) -> RSAPrivateKey:
        """
        同步加载签名密钥 RSA 私钥

        :param record: 数据库中的签名密钥记录
        :param now: 可注入的当前时间
        :param require_active: 是否要求密钥处于 active 状态
        :return: 已验证的 RSA 私钥
        :raises KeyServiceError: 私钥不合法或无法同步加载
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(cls.load_private_key_async(record, now=now, require_active=require_active))
        raise KeyServiceError('事件循环中不能同步加载签名私钥')

    @classmethod
    async def get_signing_key(
        cls,
        db: AsyncSession,
        *,
        now: datetime | None = None,
        decrypt_private_key: Callable[[str], bytes | str | Awaitable[bytes | str]] | None = None,
    ) -> RSAPrivateKey:
        """
        获取当前 active 签名密钥的 RSA 私钥

        :param db: 异步数据库会话
        :param now: 可注入当前时间
        :param decrypt_private_key: 可注入的私钥解密回调
        :return: 已验证 RSA 私钥
        :raises KeyServiceError: 没有匹配的 active 密钥
        """

        cls._require_enabled()
        record = await OidcKeyDao.get_active(db, alg=RS256)
        if record is None:
            raise KeyServiceError('尚无可用的活动签名密钥')
        return await cls.load_private_key_async(record, now=now, decrypt_private_key=decrypt_private_key)

    @classmethod
    async def build_jwks(cls, db: AsyncSession, *, now: datetime | None = None) -> dict[str, list[dict[str, str]]]:
        """
        构造发布中的签名公钥 JWKS

        :param db: 异步数据库会话
        :param now: 可注入当前时间
        :return: 标准 ``{'keys': [...]}`` JSON 结构
        :raises KeyServiceError: OIDC 关闭或公开密钥记录不合法
        """

        cls._require_enabled()
        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        records = await OidcKeyDao.list_published(db, now=current)
        keys: list[dict[str, str]] = []
        for record in records:
            publish_at = TimezoneUtil.to_optional_utc(getattr(record, 'publish_at', None))
            remove_at = TimezoneUtil.to_optional_utc(getattr(record, 'remove_from_jwks_at', None))
            if (
                getattr(record, 'status', None) not in _PUBLISHED_STATUSES
                or getattr(record, 'alg', None) != RS256
                or publish_at is None
                or publish_at > current
                or (remove_at is not None and remove_at <= current)
            ):
                continue
            try:
                keys.append(OidcUtil.normalize_public_jwk(record, min_rsa_bits=_MIN_RSA_BITS))
            except ValueError as exc:
                raise KeyServiceError(str(exc)) from exc
        keys.sort(key=lambda item: item['kid'])

        return {'keys': keys}

    @classmethod
    async def activate_key(
        cls,
        db: AsyncSession,
        kid: str,
        *,
        now: datetime | None = None,
        decrypt_private_key: Callable[[str], bytes | str | Awaitable[bytes | str]] | None = None,
        actor: str = 'system:lifecycle',
        redis: Any = None,
    ) -> bool:
        """
        激活 pending 签名密钥并安排旧密钥退役

        :param db: 异步数据库会话，调用方负责提交事务
        :param kid: 待激活的 pending 密钥 kid
        :param now: 可注入当前时间
        :param decrypt_private_key: 可注入的私钥引用解密/加载回调
        :param actor: 操作人标识
        :param redis: 应用共享 Redis，用于跨实例轮换互斥；离线单元测试可省略
        :return: 成功完成切换时返回 True
        :raises KeyServiceError: 目标密钥未到发布时间或算法不符
        """

        cls._require_enabled(management=True)
        if not OidcUtil.is_valid_kid(kid):
            raise KeyServiceError('签名密钥标识 kid 包含不允许的字符')
        async with cls._rotation_lock(redis):
            current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
            await OidcKeyDao.lock_algorithm_for_update(db, alg=RS256)
            target = await OidcKeyDao.get_by_kid_for_update(db, kid)
            if target is None or target.alg != RS256 or target.status != 'pending':
                raise KeyServiceError('目标签名密钥不处于待激活状态')
            publish_at = TimezoneUtil.to_optional_utc(target.publish_at)
            if publish_at is None or publish_at > current:
                raise KeyServiceError('目标签名密钥尚未发布')
            old = await OidcKeyDao.get_active(db, alg=RS256, for_update=True)
            await cls.load_private_key_async(
                target,
                now=current,
                decrypt_private_key=decrypt_private_key,
                require_active=False,
                management=True,
            )
            changed = await OidcKeyDao.activate(db, kid, alg=RS256, now=current)
            if changed and old is not None and old.kid != kid:
                retention_at = current + timedelta(
                    seconds=max(
                        OidcConfig.oidc_key_rotation_overlap_seconds,
                        max(
                            OidcConfig.oidc_access_token_ttl_seconds,
                            OidcConfig.oidc_max_access_token_ttl_seconds,
                            OidcConfig.oidc_id_token_ttl_seconds,
                        )
                        + OidcConfig.oidc_allowed_clock_skew_seconds,
                    )
                )
                previous_remove_at = TimezoneUtil.to_optional_utc(old.remove_from_jwks_at)
                if previous_remove_at is None or previous_remove_at < retention_at:
                    await OidcKeyDao.set_retiring(db, old.kid, retention_at, current)
            if changed:
                await AuditService.record(
                    db,
                    OidcAuditEvent.SIGNING_KEY_ROTATED,
                    'success',
                    detail={'action': 'activated', 'kid': kid, 'actor': actor[:64]},
                )
            return changed

    @classmethod
    async def create_pending_key(
        cls,
        db: AsyncSession,
        *,
        kid: str,
        publish_at: datetime,
        activate_at: datetime | None = None,
        actor: str,
        remark: str | None = None,
        now: datetime | None = None,
    ) -> SysOidcSigningKey:
        """
        创建加密保存的 pending 签名密钥记录

        :param db: 异步数据库会话，提交边界由调用方控制
        :param kid: 新密钥标识
        :param publish_at: JWKS 发布时间
        :param activate_at: 计划签名开始时间
        :param actor: 管理员安全标识
        :param remark: 管理备注
        :param now: 可注入当前项目时间
        :return: 不含私钥明文的数据库实体
        :raises KeyServiceError: 配置、标识或密钥加密条件不满足
        """

        cls._require_enabled(management=True)
        if not isinstance(actor, str) or not actor.strip():
            raise KeyServiceError('签名密钥标识 kid 和操作者不能为空')
        if not OidcUtil.is_valid_kid(kid):
            raise KeyServiceError('签名密钥标识 kid 包含不允许的字符')
        encryption_material = str(OidcConfig.oidc_signing_key_encryption_key or '').encode()
        if len(encryption_material) < _MIN_ENCRYPTION_KEY_BYTES:
            raise KeyServiceError('签名私钥加密密钥不能为空')
        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        publish_at = TimezoneUtil.to_optional_utc(publish_at)
        activate_at = TimezoneUtil.to_optional_utc(activate_at)
        if activate_at is not None and activate_at < publish_at:
            raise KeyServiceError('密钥生效时间不得早于发布时间')
        if publish_at < current:
            raise KeyServiceError('签名密钥发布时间不得早于当前时间')
        await OidcKeyDao.lock_algorithm_for_update(db, alg=RS256)
        existing = await OidcKeyDao.get_by_kid_for_update(db, kid)
        if existing is not None:
            raise KeyServiceError('签名密钥标识 kid 已存在')
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=_MIN_RSA_BITS)
        public_jwk = OidcUtil.rsa_public_jwk(private_key.public_key(), kid)
        pem = private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        salt = secrets.token_bytes(_ENCRYPTION_SALT_BYTES)
        nonce = secrets.token_bytes(12)
        ciphertext = OidcUtil.encrypt_signing_private_key(pem, encryption_material, salt=salt, nonce=nonce)
        record = SysOidcSigningKey(
            kid=kid,
            key_use='sig',
            alg=RS256,
            public_jwk=public_jwk,
            private_key_ciphertext=ciphertext,
            status='pending',
            publish_at=publish_at,
            signing_start_at=activate_at or publish_at,
            create_by=actor[:64],
            create_time=current,
            remark=remark[:500] if isinstance(remark, str) else None,
        )
        record = await OidcKeyDao.create(db, record)
        await AuditService.record(
            db,
            OidcAuditEvent.SIGNING_KEY_ROTATED,
            'success',
            detail={'action': 'created_pending', 'kid': kid, 'actor': actor[:64]},
        )

        return record

    @classmethod
    async def bootstrap_signing_key(
        cls,
        db: AsyncSession,
        *,
        kid: str,
        actor: str,
        redis: object,
        now: datetime | None = None,
    ) -> tuple[SysOidcSigningKey, bool]:
        """
        幂等创建并激活首把 OIDC 签名密钥

        已存在可用 active 密钥时只校验并返回；否则在 Redis 轮换锁与
        数据库行锁保护下创建和激活密钥。事务提交由调用方统一处理。

        :param db: 异步数据库会话
        :param kid: 首把签名密钥标识
        :param actor: 部署操作人标识
        :param redis: 异步 Redis 客户端
        :param now: 可注入的当前项目时间
        :return: 签名密钥记录与本次是否创建新密钥
        :raises KeyServiceError: 密钥配置、状态或材料不可用
        """

        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        async with cls._rotation_lock(redis):
            records = await OidcKeyDao.lock_algorithm_for_update(db, alg=RS256)
            active = next(
                (
                    row
                    for row in reversed(records)
                    if row.status == 'active'
                    and TimezoneUtil.to_optional_utc(row.signing_start_at) is not None
                    and TimezoneUtil.to_optional_utc(row.signing_start_at) <= current
                ),
                None,
            )
            if active is not None:
                await cls.load_private_key_async(active, now=current, management=True)
                return active, False

            existing = await OidcKeyDao.get_by_kid_for_update(db, kid)
            created = existing is None
            if existing is None:
                existing = await cls.create_pending_key(
                    db,
                    kid=kid,
                    publish_at=current,
                    activate_at=current,
                    actor=actor,
                    remark='OIDC 部署初始化',
                    now=current,
                )
            elif existing.status != 'pending':
                raise KeyServiceError('初始化签名密钥不处于待激活状态')

            await cls.load_private_key_async(
                existing,
                now=current,
                require_active=False,
                management=True,
            )
            if not await OidcKeyDao.activate(db, kid, alg=RS256, now=current):
                raise KeyServiceError('初始化签名密钥激活失败')
            await AuditService.record(
                db,
                OidcAuditEvent.SIGNING_KEY_ROTATED,
                'success',
                detail={'action': 'activated', 'kid': kid, 'actor': actor[:64]},
            )
            return existing, created

    @classmethod
    async def retire_key(
        cls,
        db: AsyncSession,
        kid: str,
        *,
        now: datetime | None = None,
        actor: str = 'system:lifecycle',
    ) -> bool:
        """
        将 active 签名密钥转为 retiring 状态

        :param db: 异步数据库会话
        :param kid: 密钥标识
        :param now: 当前时间
        :param actor: 操作人标识
        :return: 本次是否将签名密钥转为退役中状态
        :raises KeyServiceError: 签名密钥状态、材料或配置不符合要求
        """

        cls._require_enabled(management=True)
        if not OidcUtil.is_valid_kid(kid):
            raise KeyServiceError('签名密钥标识 kid 包含不允许的字符')
        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        record = await OidcKeyDao.get_by_kid_for_update(db, kid)
        if record is None or record.status not in {'active', 'retiring'}:
            raise KeyServiceError('签名密钥未处于活动状态')
        if record.status == 'retiring':
            return False
        if record.status == 'active':
            active_count = sum(1 for item in await OidcKeyDao.lock_algorithm_for_update(db) if item.status == 'active')
            if active_count <= 1:
                raise KeyServiceError('必须保留至少一把有效的活动签名密钥')
        record.status = 'retiring'
        record.signing_stop_at = current
        record.remove_from_jwks_at = current + timedelta(
            seconds=max(
                OidcConfig.oidc_key_rotation_overlap_seconds,
                OidcConfig.oidc_max_access_token_ttl_seconds + OidcConfig.oidc_allowed_clock_skew_seconds,
            )
        )
        await AuditService.record(
            db,
            OidcAuditEvent.SIGNING_KEY_ROTATED,
            'success',
            detail={'action': 'retired', 'kid': kid, 'actor': actor[:64]},
        )

        return True

    @classmethod
    async def retire_due(cls, db: AsyncSession) -> int:
        """
        退役已结束 JWKS 保留期的签名密钥

        :param db: 异步数据库会话
        :return: 更新的记录数量
        """

        cls._require_enabled()

        return await OidcKeyDao.retire_due(db)

    @classmethod
    async def activate_due(
        cls,
        db: AsyncSession,
        *,
        redis: Any = None,
        now: datetime | None = None,
        audit_writer: Callable[..., Awaitable[Any]] | None = None,
    ) -> int:
        """
        批量激活已到签名开始时间的 pending 密钥

        :param db: 异步数据库会话；每次状态推进由调用方提交
        :param redis: 应用共享 Redis 轮换锁客户端
        :param now: 可注入当前项目时间
        :param audit_writer: 可注入的独立审计写入器，生产默认使用独立提交事务
        :return: 本次成功激活的密钥数量
        """

        cls._require_enabled()
        current = TimezoneUtil.to_optional_utc(now or TimezoneUtil.utc_now())
        pending = await OidcKeyDao.list_due_pending(db, now=current)
        activated = 0
        for record in pending:
            try:
                if await cls.activate_key(
                    db,
                    record.kid,
                    now=current,
                    redis=redis,
                    actor='system:lifecycle',
                ):
                    await db.commit()
                    activated += 1
            except Exception:  # noqa: PERF203
                await db.rollback()
                safe_kid = (
                    record.kid if isinstance(record.kid, str) and OidcUtil.is_valid_kid(record.kid) else 'invalid'
                )
                try:
                    writer = audit_writer or AuditService.record_independent
                    await writer(
                        db,
                        OidcAuditEvent.SIGNING_KEY_ROTATED,
                        'failure',
                        failure_code='key_activation_failed',
                        detail={'action': 'activation_failed', 'kid': safe_kid},
                    )
                except Exception:
                    logger.warning('OIDC 签名密钥激活审计记录写入失败，密钥标识={}', safe_kid)
                logger.warning('OIDC 签名密钥激活失败，事件=signing_key_rotated，密钥标识={}', safe_kid)
        return activated

    @classmethod
    async def delete_key(
        cls,
        db: AsyncSession,
        kid: str,
        *,
        actor: str = 'system:lifecycle',
    ) -> bool:
        """
        删除已退役且超过 JWKS 保留期的签名密钥

        :param db: 异步数据库会话
        :param kid: 待删除的 kid
        :param actor: 操作人标识
        :return: 删除成功时返回 True
        :raises KeyServiceError: 密钥仍可能用于验签或不存在
        """

        cls._require_enabled(management=True)
        if not OidcUtil.is_valid_kid(kid):
            raise KeyServiceError('签名密钥标识 kid 包含不允许的字符')
        record = await OidcKeyDao.get_by_kid_for_update(db, kid)
        if record is None or record.status != 'retired':
            raise KeyServiceError('签名密钥尚未完成安全退役')
        remove_at = TimezoneUtil.to_optional_utc(record.remove_from_jwks_at)
        if remove_at is None or remove_at > TimezoneUtil.utc_now():
            raise KeyServiceError('签名密钥仍在 JWKS 公钥保留期内')
        if not await OidcKeyDao.delete_retired(db, kid):
            raise KeyServiceError('签名密钥删除失败')
        await AuditService.record(
            db,
            OidcAuditEvent.SIGNING_KEY_ROTATED,
            'success',
            detail={'action': 'deleted', 'kid': kid, 'actor': actor[:64]},
        )

        return True


class OidcKeyManagementService:
    """
    OIDC 签名密钥管理模块服务层
    """

    _ERROR_MESSAGES = {
        '目标签名密钥不处于待激活状态': '签名密钥状态已变化，请刷新列表后重试',
        '目标签名密钥尚未发布': '签名公钥尚未到公开时间，暂时不能开始使用',
        '签名密钥正在轮换，请稍后重试': '其他实例正在处理签名密钥，请稍后重试',
    }

    @staticmethod
    def view(row: SysOidcSigningKey) -> dict[str, object]:
        """
        将签名密钥 ORM 记录转换为管理视图

        :param row: 签名密钥 ORM 记录
        :return: 签名密钥管理视图字段映射
        """

        return OidcKeyViewModel(
            kid=row.kid,
            key_use=row.key_use,
            alg=row.alg,
            public_jwk=row.public_jwk,
            status=row.status,
            publish_at=TimezoneUtil.to_optional_utc(row.publish_at),
            signing_start_at=TimezoneUtil.to_optional_utc(row.signing_start_at),
            signing_stop_at=TimezoneUtil.to_optional_utc(row.signing_stop_at),
            remove_from_jwks_at=TimezoneUtil.to_optional_utc(row.remove_from_jwks_at),
            create_time=TimezoneUtil.to_optional_utc(row.create_time),
        ).model_dump(by_alias=True)

    @classmethod
    async def bootstrap(
        cls,
        db: AsyncSession,
        *,
        kid: str,
        actor: str,
        redis: object,
        now: datetime | None = None,
    ) -> tuple[dict[str, object], bool]:
        """
        幂等创建并激活首把 OIDC 签名密钥

        已存在可用 active 密钥时只校验并返回；否则在 Redis 轮换锁与
        数据库行锁保护下创建、激活并提交，适合部署流水线并发调用。

        :param db: 异步数据库会话
        :param kid: 首把签名密钥标识
        :param actor: 部署操作人标识
        :param redis: 异步 Redis 客户端
        :param now: 可注入的当前项目时间
        :return: 管理视图与本次是否创建新密钥
        :raises ServiceException: 签名密钥初始化失败
        """

        row, created = await cls._execute(
            db,
            lambda: KeyService.bootstrap_signing_key(
                db,
                kid=kid,
                actor=actor,
                redis=redis,
                now=now,
            ),
        )
        await db.refresh(row)

        return cls.view(row), created

    @classmethod
    async def list_page(
        cls,
        db: AsyncSession,
        status: Literal['pending', 'active', 'retiring', 'retired', 'compromised'] | None,
        page_num: int,
        page_size: int,
    ) -> tuple[list[dict[str, object]], int]:
        """
        分页查询签名密钥管理视图

        :param db: 异步数据库会话
        :param status: 密钥状态筛选值
        :param page_num: 页码
        :param page_size: 页大小
        :return: 管理视图列表和总数
        """

        rows = await OidcKeyDao.list_admin(db, status=status, offset=(page_num - 1) * page_size, limit=page_size)
        total = await OidcKeyDao.count_admin(db, status=status)

        return [cls.view(row) for row in rows], total

    @staticmethod
    async def rotate(db: AsyncSession, payload: OidcKeyRotateModel, actor: str) -> dict[str, object]:
        """
        创建 pending 签名密钥并返回管理视图

        :param db: 异步数据库会话
        :param payload: 签名密钥轮换参数
        :param actor: 操作人标识
        :return: 新建签名密钥的管理视图字段映射
        """

        result = await OidcKeyManagementService._execute(
            db,
            lambda: KeyService.create_pending_key(
                db,
                kid=payload.kid,
                publish_at=payload.publish_at,
                activate_at=payload.activate_at,
                actor=actor,
                remark=payload.remark,
            ),
        )

        return OidcKeyManagementService.view(result)

    @staticmethod
    async def activate(db: AsyncSession, kid: str, actor: str, redis: object) -> bool:
        """
        激活指定签名密钥并提交事务

        :param db: 异步数据库会话
        :param kid: 密钥标识
        :param actor: 操作人标识
        :param redis: 异步 Redis 客户端
        :return: 本次是否激活签名密钥
        :raises ServiceException: 签名密钥无法开始使用
        """

        return await OidcKeyManagementService._execute(
            db, lambda: KeyService.activate_key(db, kid, actor=actor, redis=redis)
        )

    @staticmethod
    async def retire(db: AsyncSession, kid: str, actor: str) -> bool:
        """
        退役指定签名密钥并提交事务

        :param db: 异步数据库会话
        :param kid: 密钥标识
        :param actor: 操作人标识
        :return: 本次是否将签名密钥转为退役中状态
        """

        return await OidcKeyManagementService._execute(db, lambda: KeyService.retire_key(db, kid, actor=actor))

    @staticmethod
    async def delete(db: AsyncSession, kid: str, actor: str) -> bool:
        """
        删除指定已退役签名密钥并提交事务

        :param db: 异步数据库会话
        :param kid: 密钥标识
        :param actor: 操作人标识
        :return: 本次是否删除签名密钥
        """

        return await OidcKeyManagementService._execute(db, lambda: KeyService.delete_key(db, kid, actor=actor))

    @staticmethod
    async def _execute(db: AsyncSession, operation: Callable[[], Awaitable[T]]) -> T:
        """
        执行签名密钥管理事务并统一处理回滚

        :param db: 异步数据库会话
        :param operation: 事务操作回调
        :return: operation 回调的返回值
        :raises ServiceException: 签名密钥管理事务失败时抛出
        """

        try:
            result = await operation()
            await db.commit()
            return result
        except ServiceException:
            await db.rollback()
            raise
        except KeyServiceError as exc:
            await db.rollback()
            message = OidcKeyManagementService._ERROR_MESSAGES.get(str(exc), 'OIDC 签名密钥操作失败')
            raise ServiceException(message=message) from exc
        except Exception as exc:
            await db.rollback()
            raise ServiceException(message='OIDC 签名密钥操作失败') from exc
