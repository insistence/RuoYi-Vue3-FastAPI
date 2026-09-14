from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.oidc_key_do import SysOidcSigningKey
from utils.time_util import TimezoneUtil


class OidcKeyDao:
    """
    OIDC Key 数据库操作层
    """

    @classmethod
    async def get_active(
        cls, db: AsyncSession, alg: str = 'RS256', for_update: bool = False
    ) -> SysOidcSigningKey | None:
        """
        按签名算法查询活跃 OIDC Signing Key

        :param db: orm对象
        :param alg: 签名算法
        :param for_update: 是否锁定查询结果
        :return: 活跃 OIDC Signing Key，不存在时返回 None
        """

        query = select(SysOidcSigningKey).where(
            SysOidcSigningKey.status == 'active',
            SysOidcSigningKey.alg == alg,
            SysOidcSigningKey.signing_start_at <= TimezoneUtil.utc_now(),
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query.order_by(SysOidcSigningKey.signing_start_at.desc()))

        return result.scalars().first()

    @classmethod
    async def list_published(cls, db: AsyncSession, now: datetime | None = None) -> Sequence[SysOidcSigningKey]:
        """
        查询已发布的 OIDC Signing Key

        :param db: orm对象
        :param now: 当前时间
        :return: 已发布的 OIDC Signing Key 序列
        """

        current = now or TimezoneUtil.utc_now()
        result = await db.execute(
            select(SysOidcSigningKey)
            .where(
                SysOidcSigningKey.status.in_(['pending', 'active', 'retiring']),
                SysOidcSigningKey.publish_at <= current,
                (SysOidcSigningKey.remove_from_jwks_at.is_(None) | (SysOidcSigningKey.remove_from_jwks_at > current)),
            )
            .order_by(SysOidcSigningKey.create_time)
        )

        return result.scalars().all()

    @classmethod
    async def get_verifying(cls, db: AsyncSession, kid: str, now: datetime) -> SysOidcSigningKey | None:
        """
        按 kid 查询可用于验签的 OIDC Signing Key

        :param db: orm对象
        :param kid: Signing Key 标识
        :param now: 当前时间
        :return: 可验签的 OIDC Signing Key，不存在时返回 None
        """

        result = await db.execute(
            select(SysOidcSigningKey).where(
                SysOidcSigningKey.kid == kid,
                SysOidcSigningKey.alg == 'RS256',
                SysOidcSigningKey.status.in_(['active', 'retiring']),
                SysOidcSigningKey.publish_at <= now,
                (SysOidcSigningKey.remove_from_jwks_at.is_(None) | (SysOidcSigningKey.remove_from_jwks_at > now)),
            )
        )

        return result.scalars().first()

    @classmethod
    async def list_admin(
        cls, db: AsyncSession, *, status: str | None = None, offset: int = 0, limit: int = 200
    ) -> Sequence[SysOidcSigningKey]:
        """
        分页查询管理端 OIDC Signing Key

        :param db: orm对象
        :param status: 状态过滤值
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: 管理端 OIDC Signing Key 序列
        """

        query = select(SysOidcSigningKey)
        if status:
            query = query.where(SysOidcSigningKey.status == status)
        result = await db.execute(
            query.order_by(SysOidcSigningKey.create_time.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 200))
        )

        return result.scalars().all()

    @classmethod
    async def list_due_pending(cls, db: AsyncSession, now: datetime | None = None) -> Sequence[SysOidcSigningKey]:
        """
        查询待发布时间已到的 OIDC Signing Key

        :param db: orm对象
        :param now: 当前时间
        :return: 待激活 OIDC Signing Key 序列
        """

        current = now or TimezoneUtil.utc_now()
        result = await db.execute(
            select(SysOidcSigningKey)
            .where(
                SysOidcSigningKey.alg == 'RS256',
                SysOidcSigningKey.status == 'pending',
                SysOidcSigningKey.publish_at <= current,
                SysOidcSigningKey.signing_start_at <= current,
            )
            .order_by(SysOidcSigningKey.signing_start_at, SysOidcSigningKey.key_pk)
        )

        return result.scalars().all()

    @classmethod
    async def count_admin(cls, db: AsyncSession, *, status: str | None = None) -> int:
        """
        统计管理端 OIDC Signing Key 数量

        :param db: orm对象
        :param status: 状态过滤值
        :return: 管理端 OIDC Signing Key 数量
        """

        query = select(func.count()).select_from(SysOidcSigningKey)
        if status:
            query = query.where(SysOidcSigningKey.status == status)
        result = await db.execute(query)

        return int(result.scalar_one())

    @classmethod
    async def get_by_kid_for_update(cls, db: AsyncSession, kid: str) -> SysOidcSigningKey | None:
        """
        按 kid 锁定查询 OIDC Signing Key

        :param db: orm对象
        :param kid: Signing Key 标识
        :return: OIDC Signing Key，不存在时返回 None
        """

        result = await db.execute(select(SysOidcSigningKey).where(SysOidcSigningKey.kid == kid).with_for_update())

        return result.scalars().first()

    @classmethod
    async def create(cls, db: AsyncSession, record: SysOidcSigningKey) -> SysOidcSigningKey:
        """
        新增 OIDC Signing Key 并刷新主键

        :param db: orm对象
        :param record: OIDC Signing Key 对象
        :return: 已写入的 OIDC Signing Key
        """

        db.add(record)
        await db.flush()

        return record

    @classmethod
    async def set_retiring(
        cls,
        db: AsyncSession,
        kid: str,
        remove_from_jwks_at: datetime,
        now: datetime,
    ) -> bool:
        """
        设置 OIDC Signing Key 退役信息

        :param db: orm对象
        :param kid: Signing Key 标识
        :param remove_from_jwks_at: 从 JWKS 移除时间
        :param now: 当前时间
        :return: 是否更新成功
        """

        result = await db.execute(
            update(SysOidcSigningKey)
            .where(SysOidcSigningKey.kid == kid, SysOidcSigningKey.status.in_(['active', 'retiring']))
            .values(status='retiring', signing_stop_at=now, remove_from_jwks_at=remove_from_jwks_at)
        )

        return bool(result.rowcount)

    @classmethod
    async def delete_retired(cls, db: AsyncSession, kid: str) -> bool:
        """
        删除已退役的 OIDC Signing Key

        :param db: orm对象
        :param kid: Signing Key 标识
        :return: 是否删除成功
        """

        result = await db.execute(delete(SysOidcSigningKey).where(SysOidcSigningKey.kid == kid))

        return bool(result.rowcount)

    @classmethod
    async def lock_algorithm_for_update(cls, db: AsyncSession, alg: str = 'RS256') -> Sequence[SysOidcSigningKey]:
        """
        按签名算法锁定查询 OIDC Signing Key

        :param db: orm对象
        :param alg: 签名算法
        :return: 同一算法的 OIDC Signing Key 序列
        """

        result = await db.execute(
            select(SysOidcSigningKey)
            .where(SysOidcSigningKey.alg == alg)
            .order_by(SysOidcSigningKey.key_pk)
            .with_for_update()
        )

        return result.scalars().all()

    @classmethod
    async def activate(cls, db: AsyncSession, kid: str, alg: str = 'RS256', now: datetime | None = None) -> bool:
        """
        激活 OIDC Signing Key

        :param db: orm对象
        :param kid: Signing Key 标识
        :param alg: 签名算法
        :param now: 当前时间
        :return: 是否激活成功
        """

        current = now or TimezoneUtil.utc_now()
        await cls.lock_algorithm_for_update(db, alg=alg)
        target_result = await db.execute(
            select(SysOidcSigningKey)
            .where(SysOidcSigningKey.kid == kid, SysOidcSigningKey.alg == alg)
            .with_for_update()
        )
        target = target_result.scalars().first()
        if target is None or target.status != 'pending':
            return False
        await db.execute(
            update(SysOidcSigningKey)
            .where(SysOidcSigningKey.alg == alg, SysOidcSigningKey.status == 'active')
            .values(status='retiring', signing_stop_at=current)
        )
        result = await db.execute(
            update(SysOidcSigningKey)
            .where(
                SysOidcSigningKey.kid == kid,
                SysOidcSigningKey.alg == alg,
                SysOidcSigningKey.status == 'pending',
            )
            .values(status='active', signing_start_at=current)
        )

        return bool(result.rowcount)

    @classmethod
    async def mark_compromised(cls, db: AsyncSession, kid: str) -> bool:
        """
        标记 OIDC Signing Key 已泄露

        :param db: orm对象
        :param kid: Signing Key 标识
        :return: 是否标记成功
        """

        result = await db.execute(
            update(SysOidcSigningKey)
            .where(SysOidcSigningKey.kid == kid, SysOidcSigningKey.status != 'retired')
            .values(status='compromised', signing_stop_at=TimezoneUtil.utc_now())
        )

        return bool(result.rowcount)

    @classmethod
    async def retire_due(cls, db: AsyncSession) -> int:
        """
        处理到期退役的 OIDC Signing Key

        :param db: orm对象
        :return: 已退役的 OIDC Signing Key 数量
        """

        result = await db.execute(
            update(SysOidcSigningKey)
            .where(
                SysOidcSigningKey.status == 'retiring',
                SysOidcSigningKey.remove_from_jwks_at.is_not(None),
                SysOidcSigningKey.remove_from_jwks_at <= TimezoneUtil.utc_now(),
            )
            .values(status='retired')
        )

        return result.rowcount or 0
