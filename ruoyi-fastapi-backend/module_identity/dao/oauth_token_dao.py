from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.oauth_grant_do import SysOAuthRefreshToken
from utils.time_util import TimezoneUtil


class OAuthTokenDao:
    """
    OAuth Token 数据库操作层
    """

    @classmethod
    async def create(cls, db: AsyncSession, row: SysOAuthRefreshToken) -> SysOAuthRefreshToken:
        """
        新增 OAuth Refresh Token 并刷新主键

        :param db: orm对象
        :param row: OAuth Refresh Token 对象
        :return: 已写入的 OAuth Refresh Token
        """

        db.add(row)
        await db.flush()

        return row

    @classmethod
    async def get_by_token_id(
        cls, db: AsyncSession, token_id: str, for_update: bool = False
    ) -> SysOAuthRefreshToken | None:
        """
        按 Token 标识查询 OAuth Refresh Token

        :param db: orm对象
        :param token_id: Token 公开标识
        :param for_update: 是否锁定查询结果
        :return: OAuth Refresh Token，不存在时返回 None
        """

        query = select(SysOAuthRefreshToken).where(SysOAuthRefreshToken.token_id == token_id)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def get_by_hash(
        cls, db: AsyncSession, token_hash: str, for_update: bool = False
    ) -> SysOAuthRefreshToken | None:
        """
        按 Token 摘要查询 OAuth Refresh Token

        :param db: orm对象
        :param token_hash: Token 摘要
        :param for_update: 是否锁定查询结果
        :return: OAuth Refresh Token，不存在时返回 None
        """

        query = select(SysOAuthRefreshToken).where(SysOAuthRefreshToken.token_hash == token_hash)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def lock_family(cls, db: AsyncSession, family_id: str) -> Sequence[SysOAuthRefreshToken]:
        """
        锁定查询 OAuth Refresh Token 家族

        :param db: orm对象
        :param family_id: Token 家族标识
        :return: OAuth Refresh Token 序列
        """

        result = await db.execute(
            select(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.family_id == family_id)
            .order_by(SysOAuthRefreshToken.issued_at)
            .with_for_update()
        )

        return result.scalars().all()

    @classmethod
    async def family_is_active(cls, db: AsyncSession, family_id: str) -> bool:
        """
        查询 OAuth Refresh Token 家族是否活跃

        :param db: orm对象
        :param family_id: Token 家族标识
        :return: OAuth Refresh Token 家族是否活跃
        """

        rows = await cls.lock_family(db, family_id)

        return bool(rows) and not any(row.status in {'revoked', 'reuse_detected', 'family_revoked'} for row in rows)

    @classmethod
    async def list_for_sid_for_update(cls, db: AsyncSession, sid: str) -> Sequence[SysOAuthRefreshToken]:
        """
        按 Session 标识锁定查询 Refresh Token

        :param db: orm对象
        :param sid: SSO Session 标识
        :return: SSO Session 关联的 Refresh Token 序列
        """

        result = await db.execute(select(SysOAuthRefreshToken).where(SysOAuthRefreshToken.sid == sid).with_for_update())

        return result.scalars().all()

    @classmethod
    async def mark_used(
        cls,
        db: AsyncSession,
        token_id: str,
        replaced_by_token_id: str | None = None,
        *,
        now: datetime | None = None,
    ) -> bool:
        """
        标记 OAuth Refresh Token 已使用

        :param db: orm对象
        :param token_id: Token 公开标识
        :param replaced_by_token_id: 替换 Token 标识
        :param now: 当前时间
        :return: 是否更新成功
        """

        values: dict[str, object] = {'status': 'used', 'last_used_at': now or TimezoneUtil.utc_now()}
        if replaced_by_token_id is not None:
            values['replaced_by_token_id'] = replaced_by_token_id
        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.token_id == token_id, SysOAuthRefreshToken.status == 'active')
            .values(**values)
        )

        return bool(result.rowcount)

    @classmethod
    async def mark_reuse_detected(cls, db: AsyncSession, token_id: str, reason: str = 'refresh_token_reuse') -> bool:
        """
        标记 OAuth Refresh Token 重用

        :param db: orm对象
        :param token_id: Token 公开标识
        :param reason: 撤销或标记原因
        :return: 是否更新成功
        """

        now = TimezoneUtil.utc_now()
        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.token_id == token_id)
            .values(status='reuse_detected', reuse_detected_at=now, revoked_at=now, revoke_reason=reason)
        )

        return bool(result.rowcount)

    @classmethod
    async def refresh_token_family_reuse(
        cls,
        db: AsyncSession,
        family_id: str,
        offending_token_id: str,
        reason: str = 'refresh_token_reuse',
        *,
        now: datetime | None = None,
    ) -> int:
        """
        处理 OAuth Refresh Token 家族重用

        :param db: orm对象
        :param family_id: Token 家族标识
        :param offending_token_id: 检测到重用的 Token 标识
        :param reason: 撤销或标记原因
        :param now: 当前时间
        :return: 已撤销的 OAuth Refresh Token 数量
        """

        await cls.lock_family(db, family_id)
        current = now or TimezoneUtil.utc_now()
        other_result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.family_id == family_id,
                SysOAuthRefreshToken.token_id != offending_token_id,
                SysOAuthRefreshToken.status.not_in(['revoked', 'expired', 'reuse_detected']),
            )
            .values(status='revoked', revoked_at=current, revoke_reason=reason)
        )
        offending_result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.family_id == family_id, SysOAuthRefreshToken.token_id == offending_token_id)
            .values(status='reuse_detected', reuse_detected_at=current, revoked_at=current, revoke_reason=reason)
        )

        return (other_result.rowcount or 0) + (offending_result.rowcount or 0)

    @classmethod
    async def revoke_family(cls, db: AsyncSession, family_id: str, reason: str | None = None) -> int:
        """
        撤销 OAuth Refresh Token 家族

        :param db: orm对象
        :param family_id: Token 家族标识
        :param reason: 撤销或标记原因
        :return: 已撤销的 OAuth Refresh Token 数量
        """

        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.family_id == family_id, SysOAuthRefreshToken.status.not_in(['revoked', 'expired'])
            )
            .values(status='revoked', revoked_at=TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def revoke_for_user(cls, db: AsyncSession, user_id: int, reason: str | None = None) -> int:
        """
        撤销用户的 OAuth Refresh Token

        :param db: orm对象
        :param user_id: 用户编号
        :param reason: 撤销或标记原因
        :return: 已撤销的 OAuth Refresh Token 数量
        """

        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.user_id == user_id, SysOAuthRefreshToken.status.not_in(['revoked', 'expired']))
            .values(status='revoked', revoked_at=TimezoneUtil.utc_now(), revoke_reason=reason)
        )

        return result.rowcount or 0

    @classmethod
    async def revoke_for_users(
        cls, db: AsyncSession, user_ids: Sequence[int], reason: str | None = None, now: datetime | None = None
    ) -> int:
        """
        批量撤销用户的 OAuth Refresh Token

        :param db: orm对象
        :param user_ids: 用户编号序列
        :param reason: 撤销或标记原因
        :param now: 当前时间
        :return: 已撤销的 OAuth Refresh Token 数量
        """

        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.user_id.in_(user_ids),
                SysOAuthRefreshToken.status.not_in(['revoked', 'expired', 'reuse_detected']),
            )
            .values(status='revoked', revoked_at=now or TimezoneUtil.utc_now(), revoke_reason=reason)
        )
        await db.flush()

        return result.rowcount or 0

    @classmethod
    async def expire_due(cls, db: AsyncSession) -> int:
        """
        处理已到期的 OAuth Refresh Token

        :param db: orm对象
        :return: 已过期的 OAuth Refresh Token 数量
        """

        result = await db.execute(
            update(SysOAuthRefreshToken)
            .where(
                SysOAuthRefreshToken.status == 'active',
                (SysOAuthRefreshToken.idle_expires_at <= TimezoneUtil.utc_now())
                | (SysOAuthRefreshToken.absolute_expires_at <= TimezoneUtil.utc_now()),
            )
            .values(status='expired')
        )

        return result.rowcount or 0
