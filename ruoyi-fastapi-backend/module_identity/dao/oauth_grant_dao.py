from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthAccessPolicy, SysOAuthGrant, SysOAuthRefreshToken
from utils.time_util import TimezoneUtil


@dataclass(frozen=True, slots=True)
class OAuthGrantSnapshot:
    """
    OAuth Grant 可恢复快照
    """

    grant_id: str
    user_id: int
    subject_id: str
    client_pk: int
    granted_scopes: tuple[str, ...]
    granted_resources: tuple[str, ...]
    client_policy_version: int
    status: str
    consented_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None
    last_used_at: datetime | None
    remembered_scopes: tuple[str, ...] = ()
    remembered_resources: tuple[str, ...] = ()


class OAuthGrantDao:
    """
    OAuth Grant 数据库操作层
    """

    @classmethod
    async def get_by_grant_id_for_update(
        cls, db: AsyncSession, grant_id: str, *, refresh: bool = False
    ) -> SysOAuthGrant | None:
        """
        按授权标识锁定查询 OAuth Grant

        :param db: orm对象
        :param grant_id: Grant 公开标识
        :param refresh: 是否使用数据库当前值刷新已有对象
        :return: OAuth Grant，不存在时返回 None
        """

        query = select(SysOAuthGrant).where(SysOAuthGrant.grant_id == grant_id).with_for_update()
        if refresh:
            query = query.execution_options(populate_existing=True)
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def get_active_for_user_client(
        cls, db: AsyncSession, user_id: int, client_pk: int, for_update: bool = False
    ) -> SysOAuthGrant | None:
        """
        查询用户与 Client 的活跃 OAuth Grant

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param for_update: 是否锁定查询结果
        :return: 活跃 OAuth Grant，不存在时返回 None
        """

        query = select(SysOAuthGrant).where(
            SysOAuthGrant.user_id == user_id,
            SysOAuthGrant.client_pk == client_pk,
            SysOAuthGrant.status == 'active',
            (SysOAuthGrant.expires_at.is_(None) | (SysOAuthGrant.expires_at > TimezoneUtil.utc_now())),
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await db.execute(query.order_by(SysOAuthGrant.consented_at.desc()))

        return result.scalars().first()

    @classmethod
    async def list_active_for_user_client(
        cls, db: AsyncSession, user_id: int, client_pk: int
    ) -> Sequence[SysOAuthGrant]:
        """
        查询用户与 Client 的活跃 OAuth Grant 列表

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :return: 活跃 OAuth Grant 序列
        """

        result = await db.execute(
            select(SysOAuthGrant).where(
                SysOAuthGrant.user_id == user_id,
                SysOAuthGrant.client_pk == client_pk,
                SysOAuthGrant.status == 'active',
            )
        )

        return result.scalars().all()

    @classmethod
    async def merge_active_grant(
        cls,
        db: AsyncSession,
        user_id: int,
        subject_id: str,
        client_pk: int,
        granted_scopes: list[str],
        granted_resources: list[str],
        client_policy_version: int,
        expires_at: datetime | None = None,
        *,
        remember_consent: bool = True,
    ) -> SysOAuthGrant:
        """
        合并用户与 Client 的活跃 OAuth Grant

        :param db: orm对象
        :param user_id: 用户编号
        :param subject_id: 主体标识
        :param client_pk: Client 内部主键
        :param granted_scopes: 授权 Scope 编码序列
        :param granted_resources: 授权 Resource 标识序列
        :param client_policy_version: Client 策略版本
        :param expires_at: 授权过期时间
        :param remember_consent: 是否允许后续请求复用本次同意，独立于离线授权
        :return: 新增或更新后的 OAuth Grant
        """

        await OAuthAccessPolicyDao.lock_client(db, client_pk)
        grant = await cls.get_active_for_user_client(db, user_id, client_pk, for_update=True)
        now = TimezoneUtil.utc_now()
        if grant is None:
            grant = SysOAuthGrant(
                grant_id=str(uuid4()),
                user_id=user_id,
                subject_id=subject_id,
                client_pk=client_pk,
                granted_scopes=list(dict.fromkeys(granted_scopes)),
                granted_resources=list(dict.fromkeys(granted_resources)),
                remembered_scopes=list(dict.fromkeys(granted_scopes)) if remember_consent else [],
                remembered_resources=list(dict.fromkeys(granted_resources)) if remember_consent else [],
                client_policy_version=client_policy_version,
                status='active',
                consented_at=now,
                expires_at=expires_at,
            )
            db.add(grant)
        else:
            grant.subject_id = subject_id
            grant.granted_scopes = list(dict.fromkeys([*(grant.granted_scopes or []), *granted_scopes]))
            grant.granted_resources = list(dict.fromkeys([*(grant.granted_resources or []), *granted_resources]))
            grant.remembered_scopes = (
                list(dict.fromkeys([*(grant.remembered_scopes or []), *granted_scopes])) if remember_consent else []
            )
            grant.remembered_resources = (
                list(dict.fromkeys([*(grant.remembered_resources or []), *granted_resources]))
                if remember_consent
                else []
            )
            grant.client_policy_version = client_policy_version
            grant.consented_at = now
            grant.expires_at = expires_at
            grant.revoked_at = None
            grant.revoke_reason = None
        await db.flush()

        return grant

    @staticmethod
    def snapshot(grant: SysOAuthGrant) -> OAuthGrantSnapshot:
        """
        生成 OAuth Grant 可恢复快照

        :param grant: OAuth Grant 对象
        :return: OAuth Grant 快照
        """

        return OAuthGrantSnapshot(
            grant_id=grant.grant_id,
            user_id=grant.user_id,
            subject_id=grant.subject_id,
            client_pk=grant.client_pk,
            granted_scopes=tuple(grant.granted_scopes or ()),
            granted_resources=tuple(grant.granted_resources or ()),
            client_policy_version=grant.client_policy_version,
            status=grant.status,
            consented_at=grant.consented_at,
            expires_at=grant.expires_at,
            revoked_at=grant.revoked_at,
            revoke_reason=grant.revoke_reason,
            last_used_at=grant.last_used_at,
            remembered_scopes=tuple(grant.remembered_scopes or ()),
            remembered_resources=tuple(grant.remembered_resources or ()),
        )

    @classmethod
    async def restore_snapshot(
        cls,
        db: AsyncSession,
        snapshot: OAuthGrantSnapshot,
        expected: OAuthGrantSnapshot,
    ) -> bool:
        """
        恢复 OAuth Grant 可恢复快照

        :param db: orm对象
        :param snapshot: OAuth Grant 快照
        :param expected: 期望状态
        :return: 是否恢复成功
        """

        await OAuthAccessPolicyDao.lock_client(db, snapshot.client_pk)
        grant = await cls.get_by_grant_id_for_update(db, snapshot.grant_id, refresh=True)
        if grant is None or cls.snapshot(grant) != expected:
            return False
        grant.subject_id = snapshot.subject_id
        grant.granted_scopes = list(snapshot.granted_scopes)
        grant.granted_resources = list(snapshot.granted_resources)
        grant.client_policy_version = snapshot.client_policy_version
        grant.status = snapshot.status
        grant.consented_at = snapshot.consented_at
        grant.expires_at = snapshot.expires_at
        grant.revoked_at = snapshot.revoked_at
        grant.revoke_reason = snapshot.revoke_reason
        grant.last_used_at = snapshot.last_used_at
        grant.remembered_scopes = list(snapshot.remembered_scopes)
        grant.remembered_resources = list(snapshot.remembered_resources)
        await db.flush()

        return True

    @classmethod
    async def revoke_snapshot(cls, db: AsyncSession, snapshot: OAuthGrantSnapshot, reason: str) -> bool:
        """
        撤销快照对应的 OAuth Grant

        :param db: orm对象
        :param snapshot: OAuth Grant 快照
        :param reason: 撤销或标记原因
        :return: 是否撤销成功
        """

        await OAuthAccessPolicyDao.lock_client(db, snapshot.client_pk)
        grant = await cls.get_by_grant_id_for_update(db, snapshot.grant_id, refresh=True)
        if grant is None or cls.snapshot(grant) != snapshot:
            return False
        current = TimezoneUtil.utc_now()
        grant.status = 'revoked'
        grant.revoked_at = current
        grant.revoke_reason = reason
        await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.grant_id == snapshot.grant_id,
                SysOAuthRefreshToken.status.in_(['active', 'used', 'rotated']),
            )
            .values(status='revoked', revoked_at=current, revoke_reason=reason)
        )
        await db.flush()

        return True

    @classmethod
    async def get_valid_for_user_client(
        cls, db: AsyncSession, user_id: int, client_pk: int, for_update: bool = False
    ) -> SysOAuthGrant | None:
        """
        查询用户与 Client 的有效 OAuth Grant

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param for_update: 是否锁定查询结果
        :return: 有效 OAuth Grant，不存在时返回 None
        """

        query = (
            select(SysOAuthGrant)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthGrant.client_pk)
            .where(
                SysOAuthGrant.user_id == user_id,
                SysOAuthGrant.client_pk == client_pk,
                SysOAuthGrant.status == 'active',
                SysOAuthGrant.client_policy_version == SysOAuthClient.policy_version,
                (SysOAuthGrant.expires_at.is_(None) | (SysOAuthGrant.expires_at > TimezoneUtil.utc_now())),
            )
            .order_by(SysOAuthGrant.consented_at.desc())
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def revoke(cls, db: AsyncSession, grant_id: str, reason: str | None = None) -> bool:
        """
        撤销 OAuth Grant

        :param db: orm对象
        :param grant_id: Grant 公开标识
        :param reason: 撤销或标记原因
        :return: 是否撤销成功
        """

        grant = await db.execute(select(SysOAuthGrant).where(SysOAuthGrant.grant_id == grant_id).with_for_update())
        row = grant.scalars().first()
        if row is None:
            return False
        await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.grant_id == grant_id,
                SysOAuthRefreshToken.status.in_(['active', 'used', 'rotated']),
            )
            .values(status='revoked', revoked_at=TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        result = await db.execute(
            update(SysOAuthGrant)
            .where(SysOAuthGrant.grant_id == grant_id, SysOAuthGrant.status == 'active')
            .values(
                status='revoked',
                revoked_at=TimezoneUtil.utc_now(),
                revoke_reason=reason,
                remembered_scopes=[],
                remembered_resources=[],
            )
        )

        return bool(result.rowcount)

    @staticmethod
    async def targets(db: AsyncSession, grant_ids: list[str]) -> list[tuple[int, int]]:
        """
        将选中授权归并为用户和 Client，按 Client 排序以统一批量锁序

        :param db: orm对象
        :param grant_ids: 选中的授权标识
        :return: 去重后的 Client 主键和用户编号列表
        """

        result = await db.execute(
            select(SysOAuthGrant.client_pk, SysOAuthGrant.user_id)
            .where(SysOAuthGrant.grant_id.in_(grant_ids))
            .distinct()
            .order_by(SysOAuthGrant.client_pk, SysOAuthGrant.user_id)
        )
        return [(row.client_pk, row.user_id) for row in result]

    @classmethod
    async def revoke_for_user_client(cls, db: AsyncSession, user_id: int, client_pk: int, reason: str) -> list[str]:
        """
        撤销用户对 Client 的全部现有授权；调用方须先锁定 Client

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param reason: 撤销原因
        :return: 实际撤销的授权标识列表
        """

        result = await db.execute(
            select(SysOAuthGrant.grant_id)
            .where(
                SysOAuthGrant.user_id == user_id,
                SysOAuthGrant.client_pk == client_pk,
                SysOAuthGrant.status == 'active',
            )
            .order_by(SysOAuthGrant.grant_id)
            .with_for_update()
        )
        grant_ids = list(result.scalars().all())
        for grant_id in grant_ids:
            await cls.revoke(db, grant_id, reason)
        return grant_ids

    @classmethod
    async def revoke_for_user(cls, db: AsyncSession, user_id: int, reason: str | None = None) -> int:
        """
        撤销用户的 OAuth Grant

        :param db: orm对象
        :param user_id: 用户编号
        :param reason: 撤销或标记原因
        :return: 已撤销的 OAuth Grant 数量
        """

        result = await db.execute(
            update(SysOAuthGrant)
            .where(SysOAuthGrant.user_id == user_id, SysOAuthGrant.status == 'active')
            .values(status='revoked', revoked_at=TimezoneUtil.utc_now(), revoke_reason=reason)
        )

        return result.rowcount or 0

    @classmethod
    async def list_for_user(cls, db: AsyncSession, user_id: int, status: str | None = None) -> Sequence[SysOAuthGrant]:
        """
        查询用户 OAuth Grant 列表

        :param db: orm对象
        :param user_id: 用户编号
        :param status: 状态过滤值
        :return: 用户 OAuth Grant 序列
        """

        query = select(SysOAuthGrant).where(SysOAuthGrant.user_id == user_id)
        if status:
            query = query.where(SysOAuthGrant.status == status)
        result = await db.execute(query.order_by(SysOAuthGrant.consented_at.desc()))

        return result.scalars().all()

    @classmethod
    async def get_by_grant_id(cls, db: AsyncSession, grant_id: str, for_update: bool = False) -> SysOAuthGrant | None:
        """
        按授权标识查询 OAuth Grant

        :param db: orm对象
        :param grant_id: Grant 公开标识
        :param for_update: 是否锁定查询结果
        :return: OAuth Grant，不存在时返回 None
        """

        query = select(SysOAuthGrant).where(SysOAuthGrant.grant_id == grant_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        if not for_update:
            return await db.scalar(query)
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def list_page(
        cls,
        db: AsyncSession,
        *,
        user_id: int | None = None,
        client_id: str | None = None,
        status: str | None = None,
        access_status: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> Sequence[SysOAuthGrant]:
        """
        分页查询 OAuth Grant

        :param db: orm对象
        :param user_id: 用户编号
        :param client_id: Client 公开标识
        :param status: 状态过滤值
        :param access_status: 用户对应用的访问策略
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: OAuth Grant 序列
        """

        conditions = []
        if user_id is not None:
            conditions.append(SysOAuthGrant.user_id == user_id)
        if client_id is not None:
            conditions.append(SysOAuthClient.client_id == client_id)
        if status:
            effective_status = case(
                ((SysOAuthGrant.status == 'active') & (SysOAuthGrant.expires_at <= TimezoneUtil.utc_now()), 'expired'),
                else_=SysOAuthGrant.status,
            )
            conditions.append(effective_status == status)
        if access_status:
            blocked = (
                select(SysOAuthAccessPolicy.user_id)
                .where(
                    SysOAuthAccessPolicy.user_id == SysOAuthGrant.user_id,
                    SysOAuthAccessPolicy.client_pk == SysOAuthGrant.client_pk,
                    SysOAuthAccessPolicy.access_status == 'blocked',
                )
                .exists()
            )
            conditions.append(blocked if access_status == 'blocked' else ~blocked)
        query = (
            select(SysOAuthGrant)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthGrant.client_pk)
            .where(*conditions)
            .order_by(SysOAuthGrant.consented_at.desc())
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 200))
        )
        result = await db.execute(query)

        return result.scalars().all()

    @classmethod
    async def count(
        cls,
        db: AsyncSession,
        *,
        user_id: int | None = None,
        client_id: str | None = None,
        status: str | None = None,
        access_status: str | None = None,
    ) -> int:
        """
        统计 OAuth Grant 数量

        :param db: orm对象
        :param user_id: 用户编号
        :param client_id: Client 公开标识
        :param status: 状态过滤值
        :param access_status: 用户对应用的访问策略
        :return: OAuth Grant 数量
        """

        conditions = []
        if user_id is not None:
            conditions.append(SysOAuthGrant.user_id == user_id)
        if client_id is not None:
            conditions.append(SysOAuthClient.client_id == client_id)
        if status:
            effective_status = case(
                ((SysOAuthGrant.status == 'active') & (SysOAuthGrant.expires_at <= TimezoneUtil.utc_now()), 'expired'),
                else_=SysOAuthGrant.status,
            )
            conditions.append(effective_status == status)
        if access_status:
            blocked = (
                select(SysOAuthAccessPolicy.user_id)
                .where(
                    SysOAuthAccessPolicy.user_id == SysOAuthGrant.user_id,
                    SysOAuthAccessPolicy.client_pk == SysOAuthGrant.client_pk,
                    SysOAuthAccessPolicy.access_status == 'blocked',
                )
                .exists()
            )
            conditions.append(blocked if access_status == 'blocked' else ~blocked)
        result = await db.execute(
            select(func.count())
            .select_from(SysOAuthGrant)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthGrant.client_pk)
            .where(*conditions)
        )

        return int(result.scalar_one())
