from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.oauth_client_do import SysOAuthClient, SysOAuthClientSecret, SysOAuthClientUri
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.oauth_client_vo import ClientPageQueryModel
from utils.oidc_util import OidcUtil
from utils.time_util import TimezoneUtil


class OAuthClientDao:
    """
    OAuth Client 数据库操作层
    """

    @classmethod
    async def add_client(cls, db: AsyncSession, client: SysOAuthClient) -> None:
        """
        新增 OAuth Client 并刷新主键

        :param db: orm对象
        :param client: OAuth Client 对象
        :return: None
        """

        db.add(client)
        await db.flush()

    @classmethod
    async def add_uri(cls, db: AsyncSession, uri: SysOAuthClientUri) -> None:
        """
        新增 OAuth Client 回调地址并刷新主键

        :param db: orm对象
        :param uri: 回调地址
        :return: None
        """

        db.add(uri)
        await db.flush()

    @classmethod
    async def persist_client_policy_change(cls, db: AsyncSession, client: SysOAuthClient) -> None:
        """
        刷新 OAuth Client 策略变更

        :param db: orm对象
        :param client: OAuth Client 对象
        :return: None
        """

        await db.flush()

    @classmethod
    async def get_by_client_id(
        cls, db: AsyncSession, client_id: str, active_only: bool = True, for_update: bool = False
    ) -> SysOAuthClient | None:
        """
        按公开标识查询 OAuth Client

        :param db: orm对象
        :param client_id: Client 公开标识
        :param active_only: 是否仅查询启用记录
        :param for_update: 是否锁定查询结果
        :return: OAuth Client，不存在时返回 None
        """

        conditions = [SysOAuthClient.client_id == client_id]
        if active_only:
            conditions.append(SysOAuthClient.status == '0')
        query = select(SysOAuthClient).where(*conditions)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def get_by_pk(
        cls, db: AsyncSession, client_pk: int, active_only: bool = True, for_update: bool = False
    ) -> SysOAuthClient | None:
        """
        按内部主键查询 OAuth Client

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param active_only: 是否仅查询启用记录
        :param for_update: 是否锁定查询结果
        :return: OAuth Client，不存在时返回 None
        """

        conditions = [SysOAuthClient.client_pk == client_pk]
        if active_only:
            conditions.append(SysOAuthClient.status == '0')
        query = select(SysOAuthClient).where(*conditions)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().first()

    @classmethod
    async def id_map(cls, db: AsyncSession, client_pks: Sequence[int]) -> Mapping[int, str]:
        """
        批量查询 Client 主键与公开标识映射

        :param db: orm对象
        :param client_pks: Client 内部主键序列
        :return: Client 内部主键到公开标识的映射
        """

        if not client_pks:
            return {}
        result = await db.execute(
            select(SysOAuthClient.client_pk, SysOAuthClient.client_id).where(SysOAuthClient.client_pk.in_(client_pks))
        )

        return {int(client_pk): client_id for client_pk, client_id in result.all()}

    @classmethod
    async def id_for_pk(cls, db: AsyncSession, client_pk: int) -> str | None:
        """
        按内部主键查询 Client 公开标识

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: Client 公开标识，不存在时返回 None
        """

        result = await db.execute(select(SysOAuthClient.client_id).where(SysOAuthClient.client_pk == client_pk))

        return result.scalar_one_or_none()

    @classmethod
    async def has_disabled_bound_resource(cls, db: AsyncSession, client_id: str, audience: str) -> bool:
        """
        查询 Client 是否绑定停用 Resource

        :param db: orm对象
        :param client_id: Client 公开标识
        :param audience: Resource 受众
        :return: 是否绑定停用 Resource
        """

        result = await db.execute(
            select(SysOAuthResource.resource_pk)
            .join(SysOAuthClientResource, SysOAuthClientResource.resource_pk == SysOAuthResource.resource_pk)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthClientResource.client_pk)
            .where(
                SysOAuthClient.client_id == client_id,
                SysOAuthResource.audience == audience,
                SysOAuthResource.status != '0',
            )
        )

        return result.scalar_one_or_none() is not None

    @classmethod
    async def list_secrets(
        cls, db: AsyncSession, client_pk: int, active_only: bool = True, for_update: bool = False
    ) -> Sequence[SysOAuthClientSecret]:
        """
        查询 OAuth Client 密钥列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param active_only: 是否仅查询启用记录
        :param for_update: 是否锁定查询结果
        :return: OAuth Client Secret 序列
        """

        conditions = [SysOAuthClientSecret.client_pk == client_pk]
        if active_only:
            now = TimezoneUtil.utc_now()
            conditions.extend(
                [
                    SysOAuthClientSecret.status.in_(['active', 'retiring']),
                    SysOAuthClientSecret.not_before <= now,
                    (SysOAuthClientSecret.expires_at.is_(None) | (SysOAuthClientSecret.expires_at > now)),
                ]
            )
        query = select(SysOAuthClientSecret).where(*conditions).order_by(SysOAuthClientSecret.create_time)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)

        return result.scalars().all()

    @classmethod
    async def get_secret_for_update(cls, db: AsyncSession, secret_id: str) -> SysOAuthClientSecret | None:
        """
        按密钥标识锁定查询 Client Secret

        :param db: orm对象
        :param secret_id: Client Secret 标识
        :return: Client Secret，不存在时返回 None
        """

        result = await db.execute(
            select(SysOAuthClientSecret).where(SysOAuthClientSecret.secret_id == secret_id).with_for_update()
        )

        return result.scalars().first()

    @classmethod
    async def mark_secret_used(cls, db: AsyncSession, secret_id: str) -> bool:
        """
        标记 Client Secret 已使用

        :param db: orm对象
        :param secret_id: Client Secret 标识
        :return: 是否更新成功
        """

        result = await db.execute(
            update(SysOAuthClientSecret)
            .where(SysOAuthClientSecret.secret_id == secret_id)
            .values(last_used_at=TimezoneUtil.utc_now())
        )

        return bool(result.rowcount)

    @classmethod
    async def list_uris(
        cls, db: AsyncSession, client_pk: int, uri_type: str | None = None, active_only: bool = True
    ) -> Sequence[SysOAuthClientUri]:
        """
        查询 OAuth Client 回调地址列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param uri_type: 回调地址类型
        :param active_only: 是否仅查询启用记录
        :return: OAuth Client 回调地址序列
        """

        conditions = [SysOAuthClientUri.client_pk == client_pk]
        if uri_type:
            conditions.append(SysOAuthClientUri.uri_type == uri_type)
        if active_only:
            conditions.append(SysOAuthClientUri.status == '0')
        result = await db.execute(select(SysOAuthClientUri).where(*conditions).order_by(SysOAuthClientUri.uri_id))

        return result.scalars().all()

    @classmethod
    async def find_exact_uri(
        cls, db: AsyncSession, client_pk: int, uri_type: str, uri: str
    ) -> SysOAuthClientUri | None:
        """
        按完整地址查询 OAuth Client 回调地址

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param uri_type: 回调地址类型
        :param uri: 回调地址
        :return: Client 回调地址，不存在时返回 None
        """

        result = await db.execute(
            select(SysOAuthClientUri).where(
                SysOAuthClientUri.client_pk == client_pk,
                SysOAuthClientUri.uri_type == uri_type,
                SysOAuthClientUri.uri_hash == OidcUtil.sha256_digest(uri),
                SysOAuthClientUri.uri == uri,
                SysOAuthClientUri.status == '0',
            )
        )

        return result.scalars().first()

    @classmethod
    async def find_uri(
        cls, db: AsyncSession, client_pk: int, uri_type: str, uri_hash: str, uri: str
    ) -> SysOAuthClientUri | None:
        """
        按地址摘要查询 OAuth Client 回调地址

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param uri_type: 回调地址类型
        :param uri_hash: 回调地址摘要
        :param uri: 回调地址
        :return: Client 回调地址，不存在时返回 None
        """

        result = await db.execute(
            select(SysOAuthClientUri).where(
                SysOAuthClientUri.client_pk == client_pk,
                SysOAuthClientUri.uri_type == uri_type,
                SysOAuthClientUri.uri_hash == uri_hash,
                SysOAuthClientUri.uri == uri,
            )
        )

        return result.scalars().first()

    @classmethod
    async def get_uri_for_update(cls, db: AsyncSession, uri_id: int) -> SysOAuthClientUri | None:
        """
        按内部主键锁定查询 Client 回调地址

        :param db: orm对象
        :param uri_id: 回调地址内部主键
        :return: Client 回调地址，不存在时返回 None
        """

        result = await db.execute(select(SysOAuthClientUri).where(SysOAuthClientUri.uri_id == uri_id).with_for_update())

        return result.scalars().first()

    @classmethod
    async def list_scope_bindings(cls, db: AsyncSession, client_pk: int) -> Sequence[SysOAuthClientScope]:
        """
        查询 Client 权限范围绑定列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: Client Scope 绑定序列
        """

        result = await db.execute(select(SysOAuthClientScope).where(SysOAuthClientScope.client_pk == client_pk))

        return result.scalars().all()

    @classmethod
    async def list_resource_bindings(cls, db: AsyncSession, client_pk: int) -> Sequence[SysOAuthClientResource]:
        """
        查询 Client Resource 绑定列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: Client Resource 绑定序列
        """

        result = await db.execute(select(SysOAuthClientResource).where(SysOAuthClientResource.client_pk == client_pk))

        return result.scalars().all()

    @classmethod
    async def list_scopes(cls, db: AsyncSession, client_pk: int) -> Sequence[SysOAuthScope]:
        """
        查询 Client 权限范围列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: OAuth Scope 序列
        """

        result = await db.execute(
            select(SysOAuthScope)
            .join(SysOAuthClientScope, SysOAuthClientScope.scope_pk == SysOAuthScope.scope_pk)
            .where(SysOAuthClientScope.client_pk == client_pk, SysOAuthScope.status == '0')
            .order_by(SysOAuthScope.scope_pk)
        )

        return result.scalars().all()

    @classmethod
    async def list_resources(cls, db: AsyncSession, client_pk: int) -> Sequence[SysOAuthResource]:
        """
        查询 Client Resource 列表

        :param db: orm对象
        :param client_pk: Client 内部主键
        :return: OAuth Resource 序列
        """

        result = await db.execute(
            select(SysOAuthResource)
            .join(SysOAuthClientResource, SysOAuthClientResource.resource_pk == SysOAuthResource.resource_pk)
            .where(SysOAuthClientResource.client_pk == client_pk, SysOAuthResource.status == '0')
            .order_by(SysOAuthResource.resource_pk)
        )

        return result.scalars().all()

    @classmethod
    async def list_scope_definitions(cls, db: AsyncSession, active_only: bool = True) -> Sequence[SysOAuthScope]:
        """
        查询启用或全部 Scope 定义

        :param db: orm对象
        :param active_only: 是否仅查询启用记录
        :return: OAuth Scope 定义序列
        """

        query = select(SysOAuthScope)
        if active_only:
            query = query.where(SysOAuthScope.status == '0')
        result = await db.execute(query.order_by(SysOAuthScope.scope_pk))

        return result.scalars().all()

    @classmethod
    async def get_active_scopes_by_codes(cls, db: AsyncSession, scope_codes: Sequence[str]) -> Sequence[SysOAuthScope]:
        """
        按编码批量查询启用 Scope

        :param db: orm对象
        :param scope_codes: Scope 编码序列
        :return: 启用的 OAuth Scope 序列
        """

        if not scope_codes:
            return ()
        result = await db.execute(
            select(SysOAuthScope).where(SysOAuthScope.scope_code.in_(scope_codes), SysOAuthScope.status == '0')
        )

        return result.scalars().all()

    @classmethod
    async def get_active_resources_by_ids(
        cls, db: AsyncSession, resource_ids: Sequence[str]
    ) -> Sequence[SysOAuthResource]:
        """
        按资源标识批量查询启用 Resource

        :param db: orm对象
        :param resource_ids: Resource 公开标识序列
        :return: 启用的 OAuth Resource 序列
        """

        if not resource_ids:
            return ()
        result = await db.execute(
            select(SysOAuthResource).where(
                SysOAuthResource.resource_id.in_(resource_ids), SysOAuthResource.status == '0'
            )
        )

        return result.scalars().all()

    @classmethod
    async def replace_bindings(
        cls,
        db: AsyncSession,
        client_pk: int,
        scope_rows: Sequence[SysOAuthScope],
        resource_rows: Sequence[SysOAuthResource],
        uri_values: Mapping[str, Sequence[str]],
        pre_authorized: set[str],
        now: datetime,
        *,
        allowed_role_keys: Sequence[str] = (),
    ) -> None:
        """
        替换 Client 的 Scope、Resource 与回调地址绑定

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param scope_rows: Scope 绑定对象序列
        :param resource_rows: Resource 绑定对象序列
        :param uri_values: 回调地址值序列
        :param pre_authorized: 是否预授权
        :param now: 当前时间
        :param allowed_role_keys: 允许向客户端发布的角色权限字符，空列表表示不发布角色
        :return: None
        """

        await db.execute(delete(SysOAuthClientScope).where(SysOAuthClientScope.client_pk == client_pk))
        await db.execute(delete(SysOAuthClientResource).where(SysOAuthClientResource.client_pk == client_pk))
        await db.execute(delete(SysOAuthClientUri).where(SysOAuthClientUri.client_pk == client_pk))
        db.add_all(
            [
                SysOAuthClientScope(
                    client_pk=client_pk,
                    scope_pk=scope.scope_pk,
                    is_default=0,
                    pre_authorized=int(scope.scope_code in pre_authorized),
                    claim_filter={'claims': ['roles'], 'allowed_role_keys': list(allowed_role_keys)}
                    if scope.scope_code == 'roles'
                    else None,
                    create_time=now,
                )
                for scope in scope_rows
            ]
        )
        db.add_all(
            [
                SysOAuthClientResource(
                    client_pk=client_pk,
                    resource_pk=resource.resource_pk,
                    is_default=int(index == 0),
                    create_time=now,
                )
                for index, resource in enumerate(resource_rows)
            ]
        )
        db.add_all(
            [
                SysOAuthClientUri(
                    client_pk=client_pk,
                    uri_type=uri_type,
                    uri=uri,
                    uri_hash=OidcUtil.sha256_digest(uri),
                    is_default=int(index == 0),
                    status='0',
                    create_time=now,
                )
                for uri_type, uris in uri_values.items()
                for index, uri in enumerate(uris)
            ]
        )

    @classmethod
    async def add_secret(cls, db: AsyncSession, secret: SysOAuthClientSecret) -> None:
        """
        新增 OAuth Client Secret 并刷新主键

        :param db: orm对象
        :param secret: OAuth Client Secret 对象
        :return: None
        """

        db.add(secret)
        await db.flush()

    @classmethod
    async def find_active_introspection_client(cls, db: AsyncSession, client_id: str) -> SysOAuthClient | None:
        """
        按公开标识查询启用的内省 OAuth Client

        :param db: orm对象
        :param client_id: Client 公开标识
        :return: 内省 OAuth Client，不存在时返回 None
        """

        result = await db.execute(
            select(SysOAuthClient).where(
                SysOAuthClient.client_id == client_id,
                SysOAuthClient.status == '0',
                SysOAuthClient.client_type == 'confidential',
                SysOAuthClient.token_endpoint_auth_method == 'client_secret_basic',
            )
        )

        return result.scalars().first()

    @classmethod
    async def lock_clients_for_resource(cls, db: AsyncSession, resource_pk: int) -> Sequence[SysOAuthClient]:
        """
        锁定查询 Resource 关联的 OAuth Client

        :param db: orm对象
        :param resource_pk: Resource 内部主键
        :return: 按 Resource 关联的 OAuth Client 序列
        """

        direct = await db.execute(
            select(SysOAuthClient.client_pk)
            .join(SysOAuthClientResource, SysOAuthClientResource.client_pk == SysOAuthClient.client_pk)
            .where(SysOAuthClientResource.resource_pk == resource_pk)
        )
        via_scope = await db.execute(
            select(SysOAuthClientScope.client_pk)
            .join(SysOAuthScope, SysOAuthScope.scope_pk == SysOAuthClientScope.scope_pk)
            .where(SysOAuthScope.resource_pk == resource_pk)
        )
        client_pks = {row[0] for row in (*direct.all(), *via_scope.all())}
        if not client_pks:
            return ()
        result = await db.execute(
            select(SysOAuthClient).where(SysOAuthClient.client_pk.in_(client_pks)).with_for_update()
        )

        return result.scalars().all()

    @classmethod
    async def lock_clients_for_scope(cls, db: AsyncSession, scope_pk: int) -> Sequence[SysOAuthClient]:
        """
        锁定查询 Scope 关联的 OAuth Client

        :param db: orm对象
        :param scope_pk: Scope 内部主键
        :return: 按 Scope 关联的 OAuth Client 序列
        """

        result = await db.execute(
            select(SysOAuthClient)
            .join(SysOAuthClientScope, SysOAuthClientScope.client_pk == SysOAuthClient.client_pk)
            .where(SysOAuthClientScope.scope_pk == scope_pk)
            .with_for_update()
        )

        return result.scalars().all()

    @classmethod
    async def revoke_client_credentials(cls, db: AsyncSession, client_pk: int, now: datetime) -> None:
        """
        撤销 OAuth Client 的全部凭据

        :param db: orm对象
        :param client_pk: Client 内部主键
        :param now: 当前时间
        :return: None
        """

        await db.execute(
            update(SysOAuthGrant)
            .where(SysOAuthGrant.client_pk == client_pk, SysOAuthGrant.status == 'active')
            .values(status='revoked', revoked_at=now, revoke_reason='client_disabled')
        )
        await db.execute(
            update(SysOAuthRefreshToken)
            .where(SysOAuthRefreshToken.client_pk == client_pk, SysOAuthRefreshToken.status == 'active')
            .values(status='revoked', revoked_at=now, revoke_reason='client_disabled')
        )

    @classmethod
    async def get_client_detail_rows(
        cls, db: AsyncSession, client_id: str
    ) -> tuple[SysOAuthClient, list[tuple[SysOAuthScope, int]], list[str], Sequence[SysOAuthClientUri]] | None:
        """
        查询 OAuth Client 详情及关联数据

        :param db: orm对象
        :param client_id: Client 公开标识
        :return: OAuth Client、Scope 绑定统计、Resource 标识和回调地址组成的元组，不存在时返回 None
        """

        client = await cls.get_by_client_id(db, client_id, active_only=False)
        if client is None:
            return None
        scopes = await db.execute(
            select(SysOAuthScope, SysOAuthClientScope.pre_authorized)
            .join(SysOAuthClientScope, SysOAuthClientScope.scope_pk == SysOAuthScope.scope_pk)
            .where(SysOAuthClientScope.client_pk == client.client_pk)
            .order_by(SysOAuthScope.scope_pk)
        )
        resources = await db.execute(
            select(SysOAuthResource.resource_id)
            .join(SysOAuthClientResource, SysOAuthClientResource.resource_pk == SysOAuthResource.resource_pk)
            .where(SysOAuthClientResource.client_pk == client.client_pk)
            .order_by(SysOAuthResource.resource_pk)
        )
        uris = await cls.list_uris(db, client.client_pk)

        return client, scopes.all(), list(resources.scalars().all()), uris

    @classmethod
    async def list_clients_page(cls, db: AsyncSession, page: ClientPageQueryModel) -> Sequence[SysOAuthClient]:
        """
        分页查询 OAuth Client

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Client 序列
        """

        conditions = []
        if page.client_name:
            conditions.append(SysOAuthClient.client_name.contains(page.client_name, autoescape=True, escape='\\'))
        if page.client_type:
            conditions.append(SysOAuthClient.client_type == page.client_type)
        if page.status:
            conditions.append(SysOAuthClient.status == page.status)
        result = await db.execute(
            select(SysOAuthClient)
            .where(*conditions)
            .order_by(SysOAuthClient.client_pk)
            .offset((page.page_num - 1) * page.page_size)
            .limit(page.page_size)
        )

        return result.scalars().all()

    @classmethod
    async def count_clients(cls, db: AsyncSession, page: ClientPageQueryModel) -> int:
        """
        统计 OAuth Client 数量

        :param db: orm对象
        :param page: 分页查询条件对象
        :return: OAuth Client 数量
        """

        conditions = []
        if page.client_name:
            conditions.append(SysOAuthClient.client_name.contains(page.client_name, autoescape=True, escape='\\'))
        if page.client_type:
            conditions.append(SysOAuthClient.client_type == page.client_type)
        if page.status:
            conditions.append(SysOAuthClient.status == page.status)
        result = await db.execute(select(func.count()).select_from(SysOAuthClient).where(*conditions))

        return int(result.scalar_one())

    @classmethod
    async def list_cors_origins(cls, db: AsyncSession) -> tuple[str, ...]:
        """
        查询 OAuth Client 跨域来源

        :param db: orm对象
        :return: 去重后的 CORS 来源元组
        """

        result = await db.execute(
            select(SysOAuthClientUri.uri)
            .join(SysOAuthClient, SysOAuthClient.client_pk == SysOAuthClientUri.client_pk)
            .where(
                SysOAuthClient.status == '0',
                SysOAuthClientUri.status == '0',
                SysOAuthClientUri.uri_type == 'cors_origin',
            )
            .order_by(SysOAuthClientUri.uri)
        )

        return tuple(dict.fromkeys(result.scalars().all()))
