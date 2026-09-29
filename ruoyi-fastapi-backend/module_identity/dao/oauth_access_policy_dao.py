from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthAccessPolicy
from utils.time_util import TimezoneUtil


class OAuthAccessPolicyDao:
    """
    用户应用访问控制数据库操作层
    """

    @staticmethod
    async def lock_client(db: AsyncSession, client_pk: int) -> None:
        """
        锁定 Client，统一授权签发、撤销和访问控制的事务顺序

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: None
        """

        await db.execute(
            update(SysOAuthClient)
            .where(SysOAuthClient.client_pk == client_pk)
            .values(policy_version=SysOAuthClient.policy_version)
        )
        await db.execute(
            select(SysOAuthClient)
            .where(SysOAuthClient.client_pk == client_pk)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def get(
        db: AsyncSession, user_id: int, client_pk: int, *, for_update: bool = False
    ) -> SysOAuthAccessPolicy | None:
        """
        查询用户对 Client 的访问策略，未配置时默认允许

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param for_update: 是否使用当前读锁定策略
        :return: 访问策略，不存在时返回 None
        """

        query = select(SysOAuthAccessPolicy).where(
            SysOAuthAccessPolicy.user_id == user_id, SysOAuthAccessPolicy.client_pk == client_pk
        )
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query.execution_options(populate_existing=True))

        return result.scalars().first()

    @classmethod
    async def is_blocked(cls, db: AsyncSession, user_id: int, client_pk: int, *, for_update: bool = False) -> bool:
        """
        判断用户是否被禁止访问 Client

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param for_update: 是否使用当前读锁定策略
        :return: 是否禁止访问
        """

        row = await cls.get(db, user_id, client_pk, for_update=for_update)
        return row is not None and row.access_status == 'blocked'

    @classmethod
    async def set_status(
        cls, db: AsyncSession, user_id: int, client_pk: int, blocked: bool, actor: str, reason: str
    ) -> SysOAuthAccessPolicy:
        """
        更新访问策略；调用方须先锁定 Client 并负责事务提交

        :param db: orm对象
        :param user_id: 用户编号
        :param client_pk: Client 内部主键
        :param blocked: 是否禁止访问
        :param actor: 操作人
        :param reason: 操作原因
        :return: 更新后的访问策略
        """

        row = await cls.get(db, user_id, client_pk, for_update=True)
        if row is None:
            row = SysOAuthAccessPolicy(user_id=user_id, client_pk=client_pk)
            db.add(row)
        row.access_status = 'blocked' if blocked else 'allowed'
        row.reason = reason
        row.update_by = actor
        row.update_time = TimezoneUtil.utc_now()
        await db.flush()

        return row

    @staticmethod
    async def list_for_grants(db: AsyncSession, targets: list[tuple[int, int]]) -> list[SysOAuthAccessPolicy]:
        """
        批量查询管理列表中用户与 Client 的访问策略

        :param db: orm对象
        :param targets: 用户编号和 Client 主键列表
        :return: 用户访问策略列表
        """

        result = await db.execute(
            select(SysOAuthAccessPolicy).where(
                tuple_(SysOAuthAccessPolicy.user_id, SysOAuthAccessPolicy.client_pk).in_(targets)
            )
        )
        return list(result.scalars().all())
