from sqlalchemy import Select, func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthAccessPolicy
from module_identity.entity.vo.oauth_session_vo import AccessPolicyPageQueryModel
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

    @staticmethod
    def _query(query: AccessPolicyPageQueryModel) -> Select:
        """
        构建独立访问策略查询，不依赖用户已有授权记录

        :param query: 访问策略分页查询参数
        :return: 包含用户与客户端名称的查询语句
        """

        statement = (
            select(SysOAuthAccessPolicy, SysUser.user_name, SysOAuthClient.client_id, SysOAuthClient.client_name)
            .join(SysUser, SysUser.user_id == SysOAuthAccessPolicy.user_id)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthAccessPolicy.client_pk)
        )
        if query.user_id is not None:
            statement = statement.where(SysOAuthAccessPolicy.user_id == query.user_id)
        if query.client_id:
            statement = statement.where(SysOAuthClient.client_id == query.client_id)
        if query.access_status:
            statement = statement.where(SysOAuthAccessPolicy.access_status == query.access_status)
        return statement

    @classmethod
    async def list_page(
        cls, db: AsyncSession, query: AccessPolicyPageQueryModel
    ) -> list[tuple[SysOAuthAccessPolicy, str, str, str]]:
        """
        分页查询访问策略及其关联名称

        :param db: orm对象
        :param query: 访问策略分页查询参数
        :return: 访问策略、用户名、客户端标识和名称的列表
        """

        result = await db.execute(
            cls._query(query)
            .order_by(
                SysOAuthAccessPolicy.update_time.desc(),
                SysOAuthAccessPolicy.user_id,
                SysOAuthAccessPolicy.client_pk,
            )
            .offset((query.page_num - 1) * query.page_size)
            .limit(query.page_size)
        )
        return list(result.all())

    @classmethod
    async def count(cls, db: AsyncSession, query: AccessPolicyPageQueryModel) -> int:
        """
        统计匹配条件的独立访问策略数量

        :param db: orm对象
        :param query: 访问策略分页查询参数
        :return: 匹配的记录总数
        """

        return int(await db.scalar(select(func.count()).select_from(cls._query(query).subquery())) or 0)
