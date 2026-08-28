"""KeyService 的私钥、公钥发布和窗口校验测试。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.constant import OidcAuditEvent
from config.database import Base
from config.env import OidcConfig
from module_identity.dao.oidc_key_dao import OidcKeyDao
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.do.oidc_key_do import SysOidcSigningKey
from module_identity.service.key_service import KeyService, KeyServiceError, OidcKeyManagementService

_MIN_TEST_RSA_BITS = 2048


@pytest_asyncio.fixture
async def data_session() -> AsyncSession:
    """仅创建密钥和审计表，隔离项目其他 ORM 的 SQLite 方言差异。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [SysOidcSigningKey.__table__, SysOAuthAuditLog.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为密钥服务测试所需的基线。"""

    values = {
        'oidc_enabled': True,
        'oidc_active_kid': 'k1',
        'oidc_signing_private_key_path': '',
        'oidc_signing_key_source': 'file',
        'oidc_signing_key_encryption_key': '',
        'oidc_signing_algorithm': 'RS256',
        'oidc_key_rotation_overlap_seconds': 86400,
        'oidc_max_access_token_ttl_seconds': 1800,
        'oidc_allowed_clock_skew_seconds': 60,
        'oidc_access_token_ttl_seconds': 600,
        'oidc_id_token_ttl_seconds': 300,
    }
    for name, value in values.items():
        monkeypatch.setattr(OidcConfig, name, value)


def _config() -> OidcConfig:
    """返回当前测试使用的全局 OIDC 配置。"""

    return OidcConfig


def _record(tmp_path: Path, *, status: str = 'active', matching: bool = True) -> SimpleNamespace:
    """生成带文件私钥和公开 JWK 的内存记录。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    n = base64url_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')).decode()
    if not matching:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_numbers()
        n = base64url_encode(other.n.to_bytes((other.n.bit_length() + 7) // 8, 'big')).decode()
    path = tmp_path / 'signing.pem'
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )

    now = datetime.now()
    return SimpleNamespace(
        kid='k1',
        alg='RS256',
        key_use='sig',
        status=status,
        signing_start_at=now - timedelta(minutes=1),
        signing_stop_at=None,
        publish_at=now - timedelta(minutes=1),
        remove_from_jwks_at=None,
        private_key_ref=str(path),
        private_key_ciphertext=None,
        public_jwk={'kty': 'RSA', 'use': 'sig', 'kid': 'k1', 'alg': 'RS256', 'n': n, 'e': 'AQAB'},
        create_time=now,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('kid', ['../key', 'key/name', r'key\\name', 'key%2Fname', 'key name', '密钥'])
async def test_key_lifecycle_rejects_unsafe_kid_before_database_access(kid: str) -> None:
    """激活、退役和删除入口统一拒绝无法安全放入路径的 kid。"""
    for operation in (KeyService.activate_key, KeyService.retire_key, KeyService.delete_key):
        with pytest.raises(KeyServiceError, match='invalid characters'):
            await operation(object(), kid)


@pytest.mark.asyncio
async def test_activate_due_processes_only_scheduled_keys_and_rolls_back_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后台只处理到期 pending，并在单项失败时回滚该项事务。"""

    class _Session:
        commits = 0
        rollbacks = 0

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            self.rollbacks += 1

    session = _Session()
    due = SimpleNamespace(kid='due-key')
    scheduled: list[str] = []

    async def due_keys(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [due]

    async def activate(*args: object, **kwargs: object) -> bool:
        scheduled.append(args[1])
        return True

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_due_pending', due_keys)
    monkeypatch.setattr(KeyService, 'activate_key', activate)
    assert await KeyService.activate_due(session) == 1
    assert scheduled == ['due-key']
    assert session.commits == 1
    assert session.rollbacks == 0

    async def fail(*args: object, **kwargs: object) -> bool:
        raise KeyServiceError('private key does not match public JWK')

    audit_events: list[tuple[object, ...]] = []

    async def audit_writer(*args: object, **kwargs: object) -> None:
        audit_events.append(args)

    monkeypatch.setattr(KeyService, 'activate_key', fail)
    assert await KeyService.activate_due(session, audit_writer=audit_writer) == 0
    assert session.rollbacks == 1
    assert audit_events and audit_events[0][1:3] == (OidcAuditEvent.SIGNING_KEY_ROTATED, 'failure')


@pytest.mark.asyncio
async def test_activate_due_audits_first_failure_and_continues_next_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """首把激活失败必须独立审计，且不得阻断后续到期密钥。"""

    class _Session:
        commits = 0
        rollbacks = 0

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            self.rollbacks += 1

    session = _Session()
    pending = [SimpleNamespace(kid='first'), SimpleNamespace(kid='second')]
    audit_events: list[dict[str, object]] = []

    async def due_keys(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return pending

    async def activate(db: object, kid: str, **kwargs: object) -> bool:
        if kid == 'first':
            raise KeyServiceError('private key does not match public JWK')
        return True

    async def audit_writer(*args: object, **kwargs: object) -> None:
        audit_events.append(kwargs)

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_due_pending', due_keys)
    monkeypatch.setattr(KeyService, 'activate_key', activate)
    assert await KeyService.activate_due(session, audit_writer=audit_writer) == 1
    assert session.rollbacks == 1 and session.commits == 1
    assert audit_events[0]['failure_code'] == 'key_activation_failed'


@pytest.mark.asyncio
async def test_activate_due_continues_when_failure_audit_writer_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """独立失败审计异常只能记录安全日志，不能阻断后续密钥。"""
    pending = [SimpleNamespace(kid='first'), SimpleNamespace(kid='second')]
    activated: list[str] = []

    class _Session:
        async def commit(self) -> None:
            pass

        async def rollback(self) -> None:
            pass

    async def due_keys(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return pending

    async def activate(db: object, kid: str, **kwargs: object) -> bool:
        if kid == 'first':
            raise KeyServiceError('activation failed')
        activated.append(kid)
        return True

    async def failed_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError('audit database unavailable')

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_due_pending', due_keys)
    monkeypatch.setattr(KeyService, 'activate_key', activate)
    assert await KeyService.activate_due(_Session(), audit_writer=failed_audit) == 1
    assert activated == ['second']


@pytest.mark.asyncio
async def test_list_due_pending_filters_schedule_and_algorithm(data_session: AsyncSession) -> None:
    """到期查询只返回 RS256、pending 且两个时间点均已到达的密钥。"""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        SysOidcSigningKey(
            kid='due',
            alg='RS256',
            status='pending',
            private_key_ref='test.pem',
            public_jwk={'kty': 'RSA'},
            publish_at=now - timedelta(seconds=1),
            signing_start_at=now - timedelta(seconds=1),
            create_by='test',
        ),
        SysOidcSigningKey(
            kid='future-publish',
            alg='RS256',
            status='pending',
            private_key_ref='test.pem',
            public_jwk={'kty': 'RSA'},
            publish_at=now + timedelta(seconds=1),
            signing_start_at=now - timedelta(seconds=1),
            create_by='test',
        ),
        SysOidcSigningKey(
            kid='future-signing',
            alg='RS256',
            status='pending',
            private_key_ref='test.pem',
            public_jwk={'kty': 'RSA'},
            publish_at=now - timedelta(seconds=1),
            signing_start_at=now + timedelta(seconds=1),
            create_by='test',
        ),
        SysOidcSigningKey(
            kid='wrong-alg',
            alg='ES256',
            status='pending',
            private_key_ref='test.pem',
            public_jwk={'kty': 'EC'},
            publish_at=now - timedelta(seconds=1),
            signing_start_at=now - timedelta(seconds=1),
            create_by='test',
        ),
        SysOidcSigningKey(
            kid='active',
            alg='RS256',
            status='active',
            private_key_ref='test.pem',
            public_jwk={'kty': 'RSA'},
            publish_at=now - timedelta(seconds=1),
            signing_start_at=now - timedelta(seconds=1),
            create_by='test',
        ),
    ]
    data_session.add_all(rows)
    await data_session.commit()
    result = await OidcKeyDao.list_due_pending(data_session, now=now)
    assert [row.kid for row in result] == ['due']


@pytest.mark.asyncio
async def test_rotation_lock_is_cross_instance_exclusive_and_releases_atomically() -> None:
    """轮换锁在 Redis 中互斥，并只允许持有者删除自己的锁。"""

    class _Redis:
        value: str | None = None

        async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
            if nx and self.value is not None:
                return False
            self.value = value
            return True

        async def eval(self, script: str, count: int, key: str, token: str) -> int:
            if self.value == token:
                self.value = None
                return 1
            return 0

    redis = _Redis()
    lock = KeyService._rotation_lock(redis)
    await lock.__aenter__()
    with pytest.raises(KeyServiceError, match='busy'):
        async with KeyService._rotation_lock(redis):
            pass
    await lock.__aexit__(None, None, None)
    assert redis.value is None


@pytest.mark.asyncio
async def test_private_key_must_match_public_jwk(tmp_path: Path) -> None:
    """公私钥不匹配时启动加载必须失败。"""
    with pytest.raises(KeyServiceError, match='does not match'):
        await KeyService.load_private_key_async(_record(tmp_path, matching=False))


@pytest.mark.asyncio
async def test_private_key_requires_active_signing_window(tmp_path: Path) -> None:
    """pending 或已停止签名的密钥不能用于签名。"""
    with pytest.raises(KeyServiceError, match='not active'):
        await KeyService.load_private_key_async(_record(tmp_path, status='pending'))


@pytest.mark.asyncio
async def test_imported_database_kid_is_validated_before_jwks_and_signing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """历史或导入记录中的非法 kid 不得进入 JWKS 或签名加载。"""
    record = _record(tmp_path)
    record.kid = 'bad/key'
    record.public_jwk['kid'] = 'bad/key'
    with pytest.raises(KeyServiceError, match='invalid characters'):
        await KeyService.load_private_key_async(record)

    with pytest.raises(KeyServiceError, match='invalid characters'):
        KeyService._normalise_public_jwk(record)

    async def published(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [record]

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_published', published)
    with pytest.raises(KeyServiceError, match='invalid characters'):
        await KeyService.build_jwks(object())


@pytest.mark.asyncio
async def test_management_key_bootstrap_is_available_when_oidc_disabled(data_session: AsyncSession) -> None:
    """OIDC 协议关闭时仍可用独立加密材料完成密钥管理引导。"""
    config = _config()
    config.oidc_enabled = False
    config.oidc_signing_key_encryption_key = 'e' * 32
    row = await KeyService.create_pending_key(
        data_session,
        kid='bootstrap-1',
        publish_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        actor='admin',
    )
    assert row.status == 'pending'
    assert row.private_key_ciphertext.startswith('v2.')


@pytest.mark.asyncio
async def test_pending_key_times_are_stored_and_returned_without_timezone(data_session: AsyncSession) -> None:
    """轮换时间应按项目约定的本地无时区格式持久化并返回。"""
    config = _config()
    config.oidc_signing_key_encryption_key = 'e' * 32
    await KeyService.create_pending_key(
        data_session,
        kid='timezone-normalized',
        publish_at=datetime(2026, 8, 27, 17, 37, 37),
        activate_at=datetime(2026, 8, 27, 17, 38, 31),
        actor='admin',
        now=datetime(2026, 8, 27, 17, 30),
    )
    await data_session.commit()
    data_session.expunge_all()

    row = (await data_session.execute(select(SysOidcSigningKey))).scalar_one()
    assert row.publish_at == datetime(2026, 8, 27, 17, 37, 37)
    assert row.signing_start_at == datetime(2026, 8, 27, 17, 38, 31)
    view = OidcKeyManagementService.view(row)
    assert view['publishAt'] == datetime(2026, 8, 27, 17, 37, 37)
    assert view['signingStartAt'] == datetime(2026, 8, 27, 17, 38, 31)


@pytest.mark.asyncio
async def test_management_bootstrap_is_idempotent_and_activates_first_key(data_session: AsyncSession) -> None:
    """部署初始化重复执行时只保留一把 active 密钥。"""
    config = _config()
    config.oidc_enabled = False
    config.oidc_signing_key_encryption_key = 'e' * 32
    now = datetime.now(timezone.utc)

    first, first_created = await OidcKeyManagementService.bootstrap(
        data_session,
        kid='bootstrap-primary',
        actor='system:deployment',
        redis=None,
        now=now,
    )
    second, second_created = await OidcKeyManagementService.bootstrap(
        data_session,
        kid='ignored-on-retry',
        actor='system:deployment',
        redis=None,
        now=now,
    )

    assert first_created is True
    assert second_created is False
    assert first['kid'] == second['kid'] == 'bootstrap-primary'
    assert first['status'] == second['status'] == 'active'
    rows = (await data_session.execute(select(SysOidcSigningKey))).scalars().all()
    assert [(row.kid, row.status) for row in rows] == [('bootstrap-primary', 'active')]


@pytest.mark.asyncio
async def test_runtime_active_key_uses_database_state_not_bootstrap_kid(tmp_path: Path) -> None:
    """在线轮换后静态旧 OIDC_ACTIVE_KID 不应阻断新 active key。"""
    record = _record(tmp_path)
    record.kid = 'new'
    record.public_jwk['kid'] = 'new'
    config = _config()
    config.oidc_active_kid = 'old'
    assert (await KeyService.load_private_key_async(record)).key_size >= _MIN_TEST_RSA_BITS


def _orm_key(record: SimpleNamespace, status: str) -> SysOidcSigningKey:
    """把内存密钥记录转换为真实 ORM 密钥。"""
    return SysOidcSigningKey(
        kid=record.kid,
        alg=record.alg,
        public_jwk=record.public_jwk,
        private_key_ref=record.private_key_ref,
        status=status,
        publish_at=record.publish_at,
        signing_start_at=record.signing_start_at,
        signing_stop_at=record.signing_stop_at,
        remove_from_jwks_at=record.remove_from_jwks_at,
        create_by='test',
        create_time=record.create_time,
    )


@pytest.mark.asyncio
async def test_real_session_rotation_persists_state_and_injected_time(
    data_session: AsyncSession, tmp_path: Path
) -> None:
    """真实 AsyncSession 轮换后恰有一个 active 且窗口和时间准确。"""
    now = datetime(2026, 1, 1)
    old = _record(tmp_path)
    new = _record(tmp_path)
    new.kid = 'new'
    new.public_jwk['kid'] = 'new'
    new.publish_at = now - timedelta(seconds=1)
    new.signing_start_at = now - timedelta(seconds=1)
    old.signing_start_at = now - timedelta(minutes=1)
    old.publish_at = now - timedelta(minutes=1)
    old_row = _orm_key(old, 'active')
    new_row = _orm_key(new, 'pending')
    data_session.add_all([old_row, new_row])
    await data_session.flush()
    config = _config()
    config.oidc_active_kid = 'old'
    config.oidc_key_rotation_overlap_seconds = 10
    config.oidc_access_token_ttl_seconds = 20
    config.oidc_max_access_token_ttl_seconds = 30
    config.oidc_id_token_ttl_seconds = 100
    config.oidc_allowed_clock_skew_seconds = 5
    assert await KeyService.activate_key(data_session, 'new', now=now)
    await data_session.commit()
    rows = (await data_session.execute(select(SysOidcSigningKey).order_by(SysOidcSigningKey.kid))).scalars().all()
    assert [(row.kid, row.status) for row in rows] == [('k1', 'retiring'), ('new', 'active')]
    active = next(row for row in rows if row.status == 'active')
    retiring = next(row for row in rows if row.status == 'retiring')
    assert active.signing_start_at == now
    assert retiring.remove_from_jwks_at == now + timedelta(seconds=105)


@pytest.mark.asyncio
async def test_manual_activation_can_override_future_signing_schedule(
    data_session: AsyncSession, tmp_path: Path
) -> None:
    """管理员明确确认后可提前启用已公开的 pending 密钥。"""
    now = datetime.now()
    target = _record(tmp_path, status='pending')
    target.publish_at = now - timedelta(minutes=5)
    target.signing_start_at = now + timedelta(hours=1)
    data_session.add(_orm_key(target, 'pending'))
    await data_session.flush()

    assert await KeyService.activate_key(data_session, target.kid, now=now)
    await data_session.commit()

    row = (await data_session.execute(select(SysOidcSigningKey))).scalar_one()
    assert row.status == 'active'
    assert row.signing_start_at == now


@pytest.mark.asyncio
async def test_real_session_rotation_rolls_back_on_key_mismatch(data_session: AsyncSession, tmp_path: Path) -> None:
    """候选私钥失败时真实事务回滚，旧 active 状态保持不变。"""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = _record(tmp_path)
    new = _record(tmp_path, matching=False)
    new.kid = 'new'
    new.public_jwk['kid'] = 'new'
    new.publish_at = now - timedelta(seconds=1)
    new.signing_start_at = now - timedelta(seconds=1)
    old.signing_start_at = now - timedelta(minutes=1)
    old.publish_at = now - timedelta(minutes=1)
    data_session.add_all([_orm_key(old, 'active'), _orm_key(new, 'pending')])
    await data_session.flush()
    await data_session.commit()
    config = _config()
    config.oidc_active_kid = 'old'
    with pytest.raises(KeyServiceError, match='does not match'):
        await KeyService.activate_key(data_session, 'new', now=now)
    await data_session.rollback()
    rows = (await data_session.execute(select(SysOidcSigningKey).order_by(SysOidcSigningKey.kid))).scalars().all()
    assert [(row.kid, row.status) for row in rows] == [('k1', 'active'), ('new', 'pending')]


@pytest.mark.asyncio
async def test_jwks_filters_private_jwk_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """JWKS 始终只输出公开字段，即使数据库 JSON 被污染。"""
    now = datetime.now(timezone.utc)
    record = _record(tmp_path)
    record.publish_at = now - timedelta(seconds=1)
    record.public_jwk['d'] = 'secret'

    async def published(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [record]

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_published', published)
    payload = await KeyService.build_jwks(object(), now=now)
    assert payload == {
        'keys': [
            {
                'kty': 'RSA',
                'use': 'sig',
                'kid': 'k1',
                'alg': 'RS256',
                'n': record.public_jwk['n'],
                'e': record.public_jwk['e'],
            }
        ]
    }
    assert 'd' not in payload['keys'][0]


@pytest.mark.asyncio
async def test_jwks_excludes_keys_outside_publish_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWKS 不发布尚未到 publish_at 或已过 remove_from_jwks_at 的密钥。"""
    now = datetime.now(timezone.utc)
    base = {
        'kty': 'RSA',
        'use': 'sig',
        'alg': 'RS256',
        'n': 'n',
        'e': 'AQAB',
    }
    records = [
        SimpleNamespace(
            kid='future',
            alg='RS256',
            key_use='sig',
            status='pending',
            publish_at=now + timedelta(seconds=1),
            remove_from_jwks_at=None,
            public_jwk={**base, 'kid': 'future'},
        ),
        SimpleNamespace(
            kid='removed',
            alg='RS256',
            key_use='sig',
            status='retiring',
            publish_at=now - timedelta(seconds=1),
            remove_from_jwks_at=now,
            public_jwk={**base, 'kid': 'removed'},
        ),
    ]

    async def published(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return records

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_published', published)
    assert await KeyService.build_jwks(object(), now=now) == {'keys': []}


@pytest.mark.asyncio
async def test_jwks_rejects_malformed_rsa_jwk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """非法 RSA n/e 不能污染 JWKS，服务选择 fail-closed。"""
    now = datetime.now(timezone.utc)
    record = _record(tmp_path)
    record.publish_at = now - timedelta(seconds=1)
    record.public_jwk['n'] = 'not-a-rsa-modulus'

    async def published(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [record]

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.list_published', published)
    with pytest.raises(KeyServiceError, match=r'base64url|RSA numbers'):
        await KeyService.build_jwks(object(), now=now)


@pytest.mark.asyncio
async def test_activation_validates_pending_private_key_before_state_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """候选密钥公私钥不匹配时不得调用状态切换。"""
    target = _record(tmp_path, status='pending', matching=False)
    target.publish_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    old = SimpleNamespace(kid='old', status='active')
    changed = False

    async def lock_algorithm(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [old, target]

    async def get_target(*args: object, **kwargs: object) -> SimpleNamespace:
        return target

    async def get_old(*args: object, **kwargs: object) -> SimpleNamespace:
        return old

    async def activate(*args: object, **kwargs: object) -> bool:
        nonlocal changed
        changed = True
        return True

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.lock_algorithm_for_update', lock_algorithm)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.get_by_kid_for_update', get_target)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.get_active', get_old)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.activate', activate)
    with pytest.raises(KeyServiceError, match='does not match'):
        await KeyService.activate_key(object(), 'k1')
    assert changed is False


@pytest.mark.asyncio
async def test_activation_retains_old_key_for_max_overlap_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """轮换将旧 active 置为 retiring，并覆盖 overlap 与 Token 安全窗口的较大值。"""
    now = datetime.now()
    target = _record(tmp_path, status='pending')
    target.publish_at = now - timedelta(seconds=1)
    old = SimpleNamespace(kid='old', status='active', remove_from_jwks_at=None)
    config = _config()
    config.oidc_key_rotation_overlap_seconds = 7200
    config.oidc_max_access_token_ttl_seconds = 1800
    config.oidc_allowed_clock_skew_seconds = 60

    async def audit(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr('module_identity.service.key_service.AuditService.record', audit)

    async def lock_algorithm(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        return [old, target]

    async def get_target(*args: object, **kwargs: object) -> SimpleNamespace:
        return target

    async def get_old(*args: object, **kwargs: object) -> SimpleNamespace:
        return old

    async def activate(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.lock_algorithm_for_update', lock_algorithm)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.get_by_kid_for_update', get_target)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.get_active', get_old)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.activate', activate)
    set_retiring = AsyncMock(return_value=True)
    monkeypatch.setattr('module_identity.service.key_service.OidcKeyDao.set_retiring', set_retiring)
    assert await KeyService.activate_key(object(), 'k1', now=now)
    set_retiring.assert_awaited_once()
    assert set_retiring.await_args.args[1:] == ('old', now + timedelta(seconds=7200), now)


def test_etag_is_stable_and_private_fields_are_not_serialized() -> None:
    """ETag 对字段顺序稳定，公开结果不含私钥字段。"""
    first = {'keys': [{'kid': 'k1', 'n': 'n', 'e': 'AQAB'}]}
    second = {'keys': [{'e': 'AQAB', 'n': 'n', 'kid': 'k1'}]}
    assert KeyService.compute_etag(first) == KeyService.compute_etag(second)
