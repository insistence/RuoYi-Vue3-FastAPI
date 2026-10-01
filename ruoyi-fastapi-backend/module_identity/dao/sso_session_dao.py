from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, func, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthRefreshToken, SysSsoSession, SysSsoSessionClient
from utils.time_util import TimezoneUtil


class SsoSessionDao:
    """
    SSO Session 数据库操作层
    """

    @classmethod
    async def create(cls, db: AsyncSession, row: SysSsoSession) -> SysSsoSession:
        """
        新增 SSO Session 并刷新主键

        :param db: orm对象
        :param row: SSO Session 对象
        :return: 已写入的 SSO Session
        """

        db.add(row)
        await db.flush()

        return row

    @classmethod
    async def get_active(
        cls, db: AsyncSession, sid: str, for_update: bool = False, now: datetime | None = None
    ) -> SysSsoSession | None:
        """
        按 Session 标识查询活跃 SSO Session

        :param db: orm对象
        :param sid: SSO Session 标识
        :param for_update: 是否锁定查询结果
        :param now: 当前时间
        :return: 活跃 SSO Session，不存在时返回 None
        """

        now = now or TimezoneUtil.utc_now()
        query = select(SysSsoSession).where(
            SysSsoSession.sid == sid,
            SysSsoSession.status == 'active',
            SysSsoSession.idle_expires_at > now,
            SysSsoSession.absolute_expires_at > now,
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def get_by_sid(cls, db: AsyncSession, sid: str, for_update: bool = False) -> SysSsoSession | None:
        """
        按 Session 标识查询 SSO Session

        :param db: orm对象
        :param sid: SSO Session 标识
        :param for_update: 是否锁定查询结果
        :return: SSO Session，不存在时返回 None
        """

        query = select(SysSsoSession).where(SysSsoSession.sid == sid)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def get_for_token(
        cls, db: AsyncSession, sid: str, *, now: datetime, allow_offline: bool = False
    ) -> SysSsoSession | None:
        """
        获取令牌校验所需的 SSO 会话

        自然过期的会话仍可用于离线授权，显式撤销的会话不可继续使用。

        :param db: orm对象
        :param sid: SSO会话标识
        :param now: 当前UTC时间
        :param allow_offline: 是否允许使用自然过期的离线授权会话
        :return: 可用于令牌校验的会话，校验失败时返回None
        """

        session = await cls.get_active(db, sid, now=now)
        if session is not None or not allow_offline:
            return session
        session = await cls.get_by_sid(db, sid)
        if (
            session is not None
            and session.status in {'active', 'expired'}
            and getattr(session, 'revoked_at', None) is None
        ):
            return session
        return None

    @classmethod
    async def touch(cls, db: AsyncSession, sid: str, idle_expires_at: datetime, now: datetime | None = None) -> bool:
        """
        更新 SSO Session 闲置过期时间

        :param db: orm对象
        :param sid: SSO Session 标识
        :param idle_expires_at: 闲置过期时间
        :param now: 当前时间
        :return: 是否更新成功
        """

        current = now or TimezoneUtil.utc_now()
        result = await db.execute(
            update(SysSsoSession)
            .where(
                SysSsoSession.sid == sid,
                SysSsoSession.status == 'active',
                SysSsoSession.idle_expires_at > current,
                SysSsoSession.absolute_expires_at > current,
                idle_expires_at <= SysSsoSession.absolute_expires_at,
            )
            .values(last_seen_at=current, idle_expires_at=idle_expires_at)
        )
        await db.flush()

        return bool(result.rowcount)

    @classmethod
    async def revoke(cls, db: AsyncSession, sid: str, reason: str | None = None, now: datetime | None = None) -> bool:
        """
        撤销 SSO Session

        :param db: orm对象
        :param sid: SSO Session 标识
        :param reason: 撤销或标记原因
        :param now: 当前时间
        :return: 是否撤销成功
        """

        result = await db.execute(
            update(SysSsoSession)
            .where(SysSsoSession.sid == sid, SysSsoSession.status.in_(('active', 'expired')))
            .values(status='revoked', revoked_at=now or TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        await db.flush()

        return bool(result.rowcount)

    @classmethod
    async def revoke_for_user(
        cls, db: AsyncSession, user_id: int, reason: str | None = None, now: datetime | None = None
    ) -> int:
        """
        撤销用户的 SSO Session

        :param db: orm对象
        :param user_id: 用户编号
        :param reason: 撤销或标记原因
        :param now: 当前时间
        :return: 已撤销的 SSO Session 数量
        """

        result = await db.execute(
            update(SysSsoSession)
            .where(SysSsoSession.user_id == user_id, SysSsoSession.status.in_(('active', 'expired')))
            .values(status='revoked', revoked_at=now or TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def revoke_for_users(
        cls,
        db: AsyncSession,
        user_ids: Sequence[int],
        reason: str | None = None,
        now: datetime | None = None,
        exclude_sid: str | None = None,
    ) -> int:
        """
        批量撤销用户的 SSO Session

        :param db: orm对象
        :param user_ids: 用户编号序列
        :param reason: 撤销或标记原因
        :param now: 当前时间
        :param exclude_sid: 排除的 SSO Session 标识
        :return: 已撤销的 SSO Session 数量
        """

        conditions = [SysSsoSession.user_id.in_(user_ids), SysSsoSession.status.in_(('active', 'expired'))]
        if exclude_sid is not None:
            conditions.append(SysSsoSession.sid != exclude_sid)
        result = await db.execute(
            update(SysSsoSession)
            .where(*conditions)
            .values(status='revoked', revoked_at=now or TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def expire_due(cls, db: AsyncSession, now: datetime | None = None) -> int:
        """
        处理已到期的 SSO Session

        :param db: orm对象
        :param now: 当前时间
        :return: 已过期的 SSO Session 数量
        """

        now = now or TimezoneUtil.utc_now()
        result = await db.execute(
            update(SysSsoSession)
            .where(
                SysSsoSession.status == 'active',
                (SysSsoSession.idle_expires_at <= now) | (SysSsoSession.absolute_expires_at <= now),
            )
            .values(status='expired')
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def list_due(
        cls, db: AsyncSession, now: datetime | None = None, for_update: bool = False
    ) -> Sequence[SysSsoSession]:
        """
        查询待过期的 SSO Session

        :param db: orm对象
        :param now: 当前时间
        :param for_update: 是否锁定查询结果
        :return: 待过期的 SSO Session 序列
        """

        current = now or TimezoneUtil.utc_now()
        query = select(SysSsoSession).where(
            SysSsoSession.status == 'active',
            (SysSsoSession.idle_expires_at <= current) | (SysSsoSession.absolute_expires_at <= current),
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().all()

    @classmethod
    async def expire(cls, db: AsyncSession, sid: str, now: datetime | None = None) -> bool:
        """
        使 SSO Session 过期

        :param db: orm对象
        :param sid: SSO Session 标识
        :param now: 当前时间
        :return: 是否过期成功
        """

        current = now or TimezoneUtil.utc_now()
        result = await db.execute(
            update(SysSsoSession)
            .where(
                SysSsoSession.sid == sid,
                SysSsoSession.status == 'active',
                (SysSsoSession.idle_expires_at <= current) | (SysSsoSession.absolute_expires_at <= current),
            )
            .values(status='expired')
        )
        await db.flush()

        return bool(result.rowcount)

    @classmethod
    async def rotate_secret(
        cls,
        db: AsyncSession,
        sid: str,
        old_secret_hash: str,
        new_secret_hash: str,
        now: datetime | None = None,
    ) -> bool:
        """
        轮换 SSO Session 密钥摘要

        :param db: orm对象
        :param sid: SSO Session 标识
        :param old_secret_hash: 旧 Session Secret 摘要
        :param new_secret_hash: 新 Session Secret 摘要
        :param now: 当前时间
        :return: 是否轮换成功
        """

        current = now or TimezoneUtil.utc_now()
        result = await db.execute(
            update(SysSsoSession)
            .where(
                SysSsoSession.sid == sid,
                SysSsoSession.status == 'active',
                SysSsoSession.session_secret_hash == old_secret_hash,
                SysSsoSession.idle_expires_at > current,
                SysSsoSession.absolute_expires_at > current,
            )
            .values(session_secret_hash=new_secret_hash, last_seen_at=current)
        )
        await db.flush()

        return bool(result.rowcount)

    @classmethod
    async def list_for_user(
        cls,
        db: AsyncSession,
        user_id: int,
        active_only: bool = False,
        for_update: bool = False,
        *,
        revocable_only: bool = False,
    ) -> Sequence[SysSsoSession]:
        """
        查询用户 SSO Session 列表

        :param db: orm对象
        :param user_id: 用户编号
        :param active_only: 是否仅查询启用记录
        :param for_update: 是否锁定查询结果
        :param revocable_only: 是否仅查询可撤销的在线或自然过期会话
        :return: 用户 SSO Session 序列
        """

        query = select(SysSsoSession).where(SysSsoSession.user_id == user_id)
        if active_only:
            query = query.where(SysSsoSession.status == 'active')
        elif revocable_only:
            query = query.where(SysSsoSession.status.in_(('active', 'expired')))
        query = query.order_by(SysSsoSession.create_time.desc())
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().all()

    @classmethod
    async def list_page(
        cls,
        db: AsyncSession,
        *,
        user_id: int | None = None,
        ip_address: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> Sequence[SysSsoSession]:
        """
        分页查询 SSO Session

        :param db: orm对象
        :param user_id: 用户编号
        :param ip_address: 客户端 IP 地址
        :param status: 状态过滤值
        :param start_time: 查询开始时间
        :param end_time: 查询结束时间
        :param offset: 分页偏移量
        :param limit: 分页大小
        :return: SSO Session 序列
        """

        conditions = []
        if user_id is not None:
            conditions.append(SysSsoSession.user_id == user_id)
        if ip_address:
            conditions.append(SysSsoSession.ip_address == ip_address)
        if status:
            current = TimezoneUtil.utc_now()
            effective_status = case(
                (
                    (SysSsoSession.status == 'active')
                    & ((SysSsoSession.idle_expires_at <= current) | (SysSsoSession.absolute_expires_at <= current)),
                    'expired',
                ),
                else_=SysSsoSession.status,
            )
            conditions.append(effective_status == status)
        if start_time is not None:
            conditions.append(SysSsoSession.create_time >= start_time)
        if end_time is not None:
            conditions.append(SysSsoSession.create_time <= end_time)
        query = (
            select(SysSsoSession)
            .where(*conditions)
            .order_by(SysSsoSession.create_time.desc())
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
        ip_address: str | None = None,
        status: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        统计 SSO Session 数量

        :param db: orm对象
        :param user_id: 用户编号
        :param ip_address: 客户端 IP 地址
        :param status: 状态过滤值
        :param start_time: 查询开始时间
        :param end_time: 查询结束时间
        :return: SSO Session 数量
        """

        conditions = []
        if user_id is not None:
            conditions.append(SysSsoSession.user_id == user_id)
        if ip_address:
            conditions.append(SysSsoSession.ip_address == ip_address)
        if status:
            current = TimezoneUtil.utc_now()
            effective_status = case(
                (
                    (SysSsoSession.status == 'active')
                    & ((SysSsoSession.idle_expires_at <= current) | (SysSsoSession.absolute_expires_at <= current)),
                    'expired',
                ),
                else_=SysSsoSession.status,
            )
            conditions.append(effective_status == status)
        if start_time is not None:
            conditions.append(SysSsoSession.create_time >= start_time)
        if end_time is not None:
            conditions.append(SysSsoSession.create_time <= end_time)
        result = await db.execute(select(func.count()).select_from(SysSsoSession).where(*conditions))

        return int(result.scalar_one())

    @classmethod
    async def record_client(cls, db: AsyncSession, sid: str, client_pk: int, now: datetime) -> None:
        """
        记录成功兑换授权码的会话与应用；调用方须先锁定 Client

        :param db: orm对象
        :param sid: SSO Session 标识
        :param client_pk: Client 内部主键
        :param now: 本次授权时间
        :return: None
        """

        row = await db.scalar(
            select(SysSsoSessionClient).where(
                SysSsoSessionClient.sid == sid, SysSsoSessionClient.client_pk == client_pk
            )
        )
        if row is None:
            db.add(SysSsoSessionClient(sid=sid, client_pk=client_pk, create_time=now, last_used_at=now))
        else:
            row.last_used_at = now
        await db.flush()

    @classmethod
    async def client_ids_for_sid(cls, db: AsyncSession, sid: str) -> Sequence[str]:
        """
        查询精确绑定该会话的参与应用，兼容升级前已有的离线凭据

        :param db: orm对象
        :param sid: SSO Session 标识
        :return: 去重后的 Client 公开标识序列
        """

        return (await cls.client_ids_for_sids(db, [sid])).get(sid, [])

    @classmethod
    async def client_ids_for_sids(cls, db: AsyncSession, sids: list[str]) -> dict[str, list[str]]:
        """
        批量查询会话关联应用，避免管理列表逐行查询

        :param db: orm对象
        :param sids: SSO Session 标识列表
        :return: 会话标识与去重客户端标识列表的映射
        """

        if not sids:
            return {}
        participants = union(
            select(SysSsoSessionClient.sid, SysSsoSessionClient.client_pk).where(SysSsoSessionClient.sid.in_(sids)),
            select(SysOAuthRefreshToken.sid, SysOAuthRefreshToken.client_pk).where(SysOAuthRefreshToken.sid.in_(sids)),
        ).subquery()
        result = await db.execute(
            select(participants.c.sid, SysOAuthClient.client_id)
            .join(SysOAuthClient, SysOAuthClient.client_pk == participants.c.client_pk)
            .order_by(participants.c.sid, SysOAuthClient.client_id)
        )
        mapping: dict[str, list[str]] = {}
        for sid, client_id in result.all():
            mapping.setdefault(sid, []).append(client_id)
        return mapping
