from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.dao._helpers import escape_like
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.oauth_resource_vo import ResourcePageQueryModel, ScopePageQueryModel


class OAuthResourceDao:
    """
    OAuth Resource 数据库操作层
    """

    @classmethod
    async def add_resource(cls, db: AsyncSession, resource: SysOAuthResource) -> None:
        """
        新增 OAuth Resource 并刷新主键

        :param db: orm对象
        :param resource: OAuth Resource 对象
        :return: None
        """
        db.add(resource)
        await db.flush()

    @classmethod
    async def add_scope(cls, db: AsyncSession, scope: SysOAuthScope) -> None:
        """
        新增 OAuth Scope 并刷新主键

        :param db: orm对象
        :param scope: OAuth Scope 对象
        :return: None
        """
        db.add(scope)
        await db.flush()

    @classmethod
    async def persist_resource_change(cls, db: AsyncSession, resource: SysOAuthResource) -> None:
        """
        刷新 OAuth Resource 变更

        :param db: orm对象
        :param resource: OAuth Resource 对象
        :return: None
        """
        await db.flush()

    @classmethod
    async def persist_scope_change(cls, db: AsyncSession, scope: SysOAuthScope) -> None:
        """
        刷新 OAuth Scope 变更

        :param db: orm对象
        :param scope: OAuth Scope 对象
        :return: None
        """
        await db.flush()

    @classmethod
    async def get_resource(
        cls, db: AsyncSession, resource_id: str, *, for_update: bool = False
    ) -> SysOAuthResource | None:
        """
        按资源标识查询 OAuth Resource

        :param db: orm对象
        :param resource_id: Resource 公开标识
        :param for_update: 是否锁定查询结果
        :return: OAuth Resource，不存在时返回 None
        """
        query = select(SysOAuthResource).where(SysOAuthResource.resource_id == resource_id)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        return result.scalars().first()

    @classmethod
    async def find_resource_duplicate(cls, db: AsyncSession, resource_id: str, audience: str) -> bool:
        """
        按资源标识和受众查询重复 Resource

        :param db: orm对象
        :param resource_id: Resource 公开标识
        :param audience: Resource 受众
        :return: 是否存在重复 Resource
        """
        result = await db.execute(
            select(SysOAuthResource.resource_pk).where(
                (SysOAuthResource.resource_id == resource_id) | (SysOAuthResource.audience == audience)
            )
        )
        return result.scalar_one_or_none() is not None

    @classmethod
    async def list_resources_page(cls, db: AsyncSession, page: ResourcePageQueryModel) -> Sequence[SysOAuthResource]:
        """
        分页查询 OAuth Resource

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Resource 序列
        """
        conditions = []
        if page.resource_name:
            conditions.append(SysOAuthResource.resource_name.like(f'%{escape_like(page.resource_name)}%', escape='\\'))
        if page.status:
            conditions.append(SysOAuthResource.status == page.status)
        result = await db.execute(
            select(SysOAuthResource)
            .where(*conditions)
            .order_by(SysOAuthResource.resource_pk)
            .offset((page.page_num - 1) * page.page_size)
            .limit(page.page_size)
        )
        return result.scalars().all()

    @classmethod
    async def count_resources(cls, db: AsyncSession, page: ResourcePageQueryModel) -> int:
        """
        统计 OAuth Resource 数量

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Resource 数量
        """
        conditions = []
        if page.resource_name:
            conditions.append(SysOAuthResource.resource_name.like(f'%{escape_like(page.resource_name)}%', escape='\\'))
        if page.status:
            conditions.append(SysOAuthResource.status == page.status)
        result = await db.execute(select(func.count()).select_from(SysOAuthResource).where(*conditions))
        return int(result.scalar_one())

    @classmethod
    async def active_resource(cls, db: AsyncSession, resource_id: str | None) -> SysOAuthResource | None:
        """
        按资源标识查询启用 OAuth Resource

        :param db: orm对象
        :param resource_id: Resource 公开标识
        :return: 启用 OAuth Resource，不存在时返回 None
        """
        if not resource_id:
            return None
        result = await db.execute(
            select(SysOAuthResource).where(SysOAuthResource.resource_id == resource_id, SysOAuthResource.status == '0')
        )
        return result.scalars().first()

    @classmethod
    async def active_by_audiences(cls, db: AsyncSession, audiences: Sequence[str]) -> Sequence[SysOAuthResource]:
        """
        按受众批量查询启用 OAuth Resource

        :param db: orm对象
        :param audiences: Resource 受众序列
        :return: 启用 OAuth Resource 序列
        """
        if not audiences:
            return ()
        result = await db.execute(
            select(SysOAuthResource).where(SysOAuthResource.audience.in_(audiences), SysOAuthResource.status == '0')
        )
        return result.scalars().all()

    @classmethod
    async def get_scope(cls, db: AsyncSession, scope_code: str, *, for_update: bool = False) -> SysOAuthScope | None:
        """
        按 Scope 编码查询 OAuth Scope

        :param db: orm对象
        :param scope_code: Scope 编码
        :param for_update: 是否锁定查询结果
        :return: OAuth Scope，不存在时返回 None
        """
        query = select(SysOAuthScope).where(SysOAuthScope.scope_code == scope_code)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        return result.scalars().first()

    @classmethod
    async def find_scope_duplicate(cls, db: AsyncSession, scope_code: str) -> bool:
        """
        按 Scope 编码查询重复 OAuth Scope

        :param db: orm对象
        :param scope_code: Scope 编码
        :return: 是否存在重复 Scope
        """
        result = await db.execute(select(SysOAuthScope.scope_pk).where(SysOAuthScope.scope_code == scope_code))
        return result.scalar_one_or_none() is not None

    @classmethod
    async def list_scopes_page(cls, db: AsyncSession, page: ScopePageQueryModel) -> Sequence[SysOAuthScope]:
        """
        分页查询 OAuth Scope

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Scope 序列
        """
        conditions = []
        if page.scope_name:
            conditions.append(SysOAuthScope.scope_name.like(f'%{escape_like(page.scope_name)}%', escape='\\'))
        if page.scope_type:
            conditions.append(SysOAuthScope.scope_type == page.scope_type)
        if page.status:
            conditions.append(SysOAuthScope.status == page.status)
        result = await db.execute(
            select(SysOAuthScope)
            .where(*conditions)
            .order_by(SysOAuthScope.scope_pk)
            .offset((page.page_num - 1) * page.page_size)
            .limit(page.page_size)
        )
        return result.scalars().all()

    @classmethod
    async def count_scopes(cls, db: AsyncSession, page: ScopePageQueryModel) -> int:
        """
        统计 OAuth Scope 数量

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Scope 数量
        """
        conditions = []
        if page.scope_name:
            conditions.append(SysOAuthScope.scope_name.like(f'%{escape_like(page.scope_name)}%', escape='\\'))
        if page.scope_type:
            conditions.append(SysOAuthScope.scope_type == page.scope_type)
        if page.status:
            conditions.append(SysOAuthScope.status == page.status)
        result = await db.execute(select(func.count()).select_from(SysOAuthScope).where(*conditions))
        return int(result.scalar_one())

    @classmethod
    async def resource_id_for_scope(cls, db: AsyncSession, resource_pk: int) -> str | None:
        """
        按 Resource 主键查询资源标识

        :param db: orm对象
        :param resource_pk: Resource 内部主键
        :return: Resource 公开标识，不存在时返回 None
        """
        result = await db.execute(
            select(SysOAuthResource.resource_id).where(SysOAuthResource.resource_pk == resource_pk)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def lock_scope_clients(cls, db: AsyncSession, scope_pk: int) -> Sequence[SysOAuthClient]:
        """
        锁定查询 Scope 关联的 OAuth Client

        :param db: orm对象
        :param scope_pk: Scope 内部主键
        :return: Scope 关联的 OAuth Client 序列
        """
        result = await db.execute(
            select(SysOAuthClient)
            .join(SysOAuthClientScope, SysOAuthClientScope.client_pk == SysOAuthClient.client_pk)
            .where(SysOAuthClientScope.scope_pk == scope_pk)
            .with_for_update()
        )
        return result.scalars().all()

    @classmethod
    async def client_ids_for_resource(cls, db: AsyncSession, resource_pk: int) -> Sequence[tuple[int, str]]:
        """
        查询 Resource 直接绑定的 Client 主键和公开标识

        :param db: orm对象
        :param resource_pk: Resource 内部主键
        :return: Client 内部主键和公开标识元组序列
        """
        result = await db.execute(
            select(SysOAuthClient.client_pk, SysOAuthClient.client_id)
            .join(SysOAuthClientResource, SysOAuthClientResource.client_pk == SysOAuthClient.client_pk)
            .where(SysOAuthClientResource.resource_pk == resource_pk)
            .order_by(SysOAuthClient.client_id)
        )
        return result.all()

    @classmethod
    async def client_ids_for_resource_scope(cls, db: AsyncSession, resource_pk: int) -> Sequence[tuple[int, str]]:
        """
        查询 Resource 通过 Scope 绑定的 Client 主键和公开标识

        :param db: orm对象
        :param resource_pk: Resource 内部主键
        :return: 通过 Scope 关联的 Client 内部主键和公开标识元组序列
        """
        result = await db.execute(
            select(SysOAuthClient.client_pk, SysOAuthClient.client_id)
            .join(SysOAuthClientScope, SysOAuthClientScope.client_pk == SysOAuthClient.client_pk)
            .join(SysOAuthScope, SysOAuthScope.scope_pk == SysOAuthClientScope.scope_pk)
            .where(SysOAuthScope.resource_pk == resource_pk)
            .order_by(SysOAuthClient.client_id)
        )
        return result.all()

    @classmethod
    async def active_grants(cls, db: AsyncSession, client_pks: Sequence[int]) -> Sequence[SysOAuthGrant]:
        """
        按 Client 主键查询活跃 OAuth Grant

        :param db: orm对象
        :param client_pks: Client 内部主键序列
        :return: 活跃 OAuth Grant 序列
        """
        if not client_pks:
            return ()
        result = await db.execute(
            select(SysOAuthGrant).where(SysOAuthGrant.status == 'active', SysOAuthGrant.client_pk.in_(client_pks))
        )
        return result.scalars().all()

    @classmethod
    async def active_refresh_tokens(cls, db: AsyncSession, client_pks: Sequence[int]) -> Sequence[SysOAuthRefreshToken]:
        """
        按 Client 主键查询活跃 Refresh Token

        :param db: orm对象
        :param client_pks: Client 内部主键序列
        :return: 活跃 OAuth Refresh Token 序列
        """
        if not client_pks:
            return ()
        result = await db.execute(
            select(SysOAuthRefreshToken).where(
                SysOAuthRefreshToken.status == 'active', SysOAuthRefreshToken.client_pk.in_(client_pks)
            )
        )
        return result.scalars().all()

    @classmethod
    async def revoke_credentials(cls, db: AsyncSession, client_pks: Sequence[int], now: datetime, reason: str) -> None:
        """
        撤销 Client 主键对应的 Grant 和 Refresh Token

        :param db: orm对象
        :param client_pks: Client 内部主键序列
        :param now: 当前时间
        :param reason: 撤销或标记原因
        :return: None
        """
        if not client_pks:
            return
        await db.execute(
            update(SysOAuthGrant)
            .where(SysOAuthGrant.client_pk.in_(client_pks), SysOAuthGrant.status == 'active')
            .values(status='revoked', revoked_at=now, revoke_reason=reason)
        )
        await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.client_pk.in_(client_pks), SysOAuthRefreshToken.status == 'active')
            .values(status='revoked', revoked_at=now, revoke_reason=reason)
        )
