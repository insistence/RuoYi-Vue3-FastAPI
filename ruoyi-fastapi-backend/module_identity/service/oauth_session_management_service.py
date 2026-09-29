from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from exceptions.exception import ServiceException
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysOAuthAccessPolicy, SysOAuthGrant, SysSsoSession
from module_identity.entity.vo.oauth_session_vo import (
    AccessPolicyModel,
    AccessPolicyPageQueryModel,
    GrantModel,
    GrantPageQueryModel,
    SessionPageQueryModel,
    SsoSessionModel,
)
from module_identity.service.audit_service import AuditService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.session_service import SsoSessionService
from utils.time_util import TimezoneUtil


class OAuthSessionManagementService:
    """
    OAuth Session 管理模块服务层
    """

    @staticmethod
    def session_view(row: SysSsoSession) -> SsoSessionModel:
        """
        将 SSO Session ORM 记录转换为 SsoSessionModel

        :param row: SSO Session ORM 记录
        :return: Session 管理视图
        """

        status = row.status
        if (
            status == 'active'
            and min(TimezoneUtil.to_utc(row.idle_expires_at), TimezoneUtil.to_utc(row.absolute_expires_at))
            <= TimezoneUtil.utc_now()
        ):
            status = 'expired'
        return SsoSessionModel(
            sid=row.sid,
            user_id=row.user_id,
            subject_id=row.subject_id,
            auth_version=row.auth_version,
            auth_time=row.auth_time,
            last_seen_at=row.last_seen_at,
            idle_expires_at=row.idle_expires_at,
            absolute_expires_at=row.absolute_expires_at,
            acr=row.acr,
            amr=list(row.amr or []),
            remember_me=bool(getattr(row, 'remember_me', False)),
            ip_address=getattr(row, 'ip_address', None),
            status=status,
            revoked_at=getattr(row, 'revoked_at', None),
            revoke_reason=getattr(row, 'revoke_reason', None),
            create_time=getattr(row, 'create_time', None),
        )

    @staticmethod
    def grant_view(row: SysOAuthGrant, client_id: str | None, policy: SysOAuthAccessPolicy | None = None) -> GrantModel:
        """
        将 OAuth Grant ORM 记录转换为 GrantModel

        :param row: OAuth Grant ORM 记录
        :param client_id: 客户端标识
        :param policy: 当前用户对应用的独立访问策略
        :return: Grant 管理视图
        """

        status = row.status
        if (
            status == 'active'
            and row.expires_at is not None
            and TimezoneUtil.to_utc(row.expires_at) <= TimezoneUtil.utc_now()
        ):
            status = 'expired'
        return GrantModel(
            grant_id=row.grant_id,
            user_id=row.user_id,
            subject_id=row.subject_id,
            client_id=client_id or '',
            granted_scopes=list(row.granted_scopes or []),
            granted_resources=list(row.granted_resources or []),
            remembered_scopes=list(getattr(row, 'remembered_scopes', None) or []),
            remembered_resources=list(getattr(row, 'remembered_resources', None) or []),
            access_status=policy.access_status if policy else 'allowed',
            access_reason=policy.reason if policy else None,
            status=status,
            client_policy_version=getattr(row, 'client_policy_version', None),
            consented_at=row.consented_at,
            last_used_at=getattr(row, 'last_used_at', None),
            expires_at=row.expires_at,
            revoke_reason=getattr(row, 'revoke_reason', None),
        )

    @staticmethod
    async def list_sessions(db: AsyncSession, query: SessionPageQueryModel) -> tuple[list[SsoSessionModel], int]:
        """
        分页查询 SSO Session

        :param db: 异步数据库会话
        :param query: Session 分页查询参数
        :return: Session 管理视图列表和总数
        """

        rows = await SsoSessionDao.list_page(
            db,
            user_id=query.user_id,
            ip_address=query.ip_address,
            status=query.status,
            start_time=query.start_time,
            end_time=query.end_time,
            offset=(query.page_num - 1) * query.page_size,
            limit=query.page_size,
        )
        total = await SsoSessionDao.count(
            db,
            user_id=query.user_id,
            ip_address=query.ip_address,
            status=query.status,
            start_time=query.start_time,
            end_time=query.end_time,
        )

        client_ids = await SsoSessionDao.client_ids_for_sids(db, [row.sid for row in rows])
        return [
            OAuthSessionManagementService.session_view(row).model_copy(
                update={'client_ids': client_ids.get(row.sid, [])}
            )
            for row in rows
        ], total

    @staticmethod
    async def get_session(db: AsyncSession, sid: str) -> SsoSessionModel | None:
        """
        按 sid 查询 SSO Session

        :param db: 异步数据库会话
        :param sid: Session 标识
        :return: Session 管理视图，不存在时返回 None
        """

        row = await SsoSessionDao.get_by_sid(db, sid)
        if row is None:
            return None
        return OAuthSessionManagementService.session_view(row).model_copy(
            update={'client_ids': list(await SsoSessionDao.client_ids_for_sid(db, sid))}
        )

    @staticmethod
    async def list_grants(db: AsyncSession, query: GrantPageQueryModel) -> tuple[list[GrantModel], int]:
        """
        分页查询 OAuth Grant

        :param db: 异步数据库会话
        :param query: Grant 分页查询参数
        :return: Grant 管理视图列表和总数
        """

        rows = await OAuthGrantDao.list_page(
            db,
            user_id=query.user_id,
            client_id=query.client_id,
            status=query.status,
            access_status=query.access_status,
            offset=(query.page_num - 1) * query.page_size,
            limit=query.page_size,
        )
        total = await OAuthGrantDao.count(
            db, user_id=query.user_id, client_id=query.client_id, status=query.status, access_status=query.access_status
        )
        keys = {int(row.client_pk) for row in rows}
        mapping = await OAuthClientDao.id_map(db, list(keys))

        policies = {
            (row.user_id, row.client_pk): row
            for row in await OAuthAccessPolicyDao.list_for_grants(db, [(row.user_id, row.client_pk) for row in rows])
        }
        return [
            OAuthSessionManagementService.grant_view(
                row, mapping.get(int(row.client_pk)), policies.get((row.user_id, row.client_pk))
            )
            for row in rows
        ], total

    @staticmethod
    async def list_access_policies(
        db: AsyncSession, query: AccessPolicyPageQueryModel
    ) -> tuple[list[AccessPolicyModel], int]:
        """
        查询独立访问策略，包含尚未授权过的用户与应用

        :param db: 异步数据库会话
        :param query: 访问策略分页查询参数
        :return: 访问策略管理视图列表和总数
        """

        rows = await OAuthAccessPolicyDao.list_page(db, query)
        total = await OAuthAccessPolicyDao.count(db, query)
        return [
            AccessPolicyModel(
                user_id=row.user_id,
                user_name=user_name,
                client_id=client_id,
                client_name=client_name,
                access_status=row.access_status,
                reason=row.reason,
                update_by=row.update_by,
                update_time=row.update_time,
            )
            for row, user_name, client_id, client_name in rows
        ], total

    @staticmethod
    async def get_grant(db: AsyncSession, grant_id: str) -> GrantModel | None:
        """
        按 grant_id 查询 OAuth Grant

        :param db: 异步数据库会话
        :param grant_id: Grant 标识
        :return: Grant 管理视图，不存在时返回 None
        """

        row = await OAuthGrantDao.get_by_grant_id(db, grant_id)
        if row is None:
            return None
        client_id = await OAuthClientDao.id_for_pk(db, row.client_pk)

        policy = await OAuthAccessPolicyDao.get(db, row.user_id, row.client_pk)
        return OAuthSessionManagementService.grant_view(row, client_id, policy)

    @staticmethod
    async def revoke_user(db: AsyncSession, redis: Redis, user_id: int, actor: str, reason: str) -> int:
        """
        撤销用户全部在线及自然过期的 SSO Session

        :param db: 异步数据库会话
        :param redis: SSO Session 热缓存客户端
        :param user_id: 用户内部标识
        :param actor: 管理操作者标识
        :param reason: 撤销原因
        :return: 实际发生状态变更的 Session 数量
        :raises ServiceException: 撤销用户 Session 事务失败
        """

        coordinator = AfterCommitCoordinator()
        try:
            count = await SsoSessionService.revoke_user(db, redis, user_id, reason=reason, coordinator=coordinator)
            await AuditService.record(
                db,
                OidcAuditEvent.SESSION_REVOKED,
                'success',
                user_id=user_id,
                detail={'actor': actor, 'reason': reason},
            )
            await coordinator.commit(db)
            return count
        except Exception as exc:
            await coordinator.rollback(db)
            raise ServiceException(message='批量撤销 Session 失败') from exc

    @staticmethod
    async def revoke_sessions(db: AsyncSession, redis: Redis, sids: list[str], actor: str, reason: str) -> int:
        """
        按 sid 集合撤销 SSO Session

        :param db: 异步数据库会话
        :param redis: SSO Session 热缓存客户端
        :param sids: Session 标识列表
        :param actor: 管理操作者标识
        :param reason: 撤销原因
        :return: 实际发生状态变更的 Session 数量
        :raises ServiceException: 批量撤销指定 Session 事务失败
        """

        coordinator, count = AfterCommitCoordinator(), 0
        try:
            for sid in sids:
                changed = await SsoSessionService.revoke(db, redis, sid, reason=reason, coordinator=coordinator)
                count += int(changed)
                if changed:
                    await AuditService.record(
                        db,
                        OidcAuditEvent.SESSION_REVOKED,
                        'success',
                        sid=sid,
                        detail={'actor': actor, 'reason': reason},
                    )
            await coordinator.commit(db)
            return count
        except Exception as exc:
            await coordinator.rollback(db)
            raise ServiceException(message='批量撤销 Session 失败') from exc

    @staticmethod
    async def revoke_grants(db: AsyncSession, grant_ids: list[str], actor: str, reason: str) -> int:
        """
        撤销选中记录所属用户对应用的全部现有授权

        :param db: 异步数据库会话
        :param grant_ids: 用于确定用户和应用的 Grant 标识集合
        :param actor: 操作人标识
        :param reason: 撤销原因
        :return: 实际撤销的 Grant 数量
        :raises ServiceException: 批量撤销 Grant 事务失败
        """

        try:
            count = 0
            for client_pk, user_id in await OAuthGrantDao.targets(db, grant_ids):
                await OAuthAccessPolicyDao.lock_client(db, client_pk)
                revoked = await OAuthGrantDao.revoke_for_user_client(db, user_id, client_pk, reason)
                client_id = await OAuthClientDao.id_for_pk(db, client_pk)
                for grant_id in revoked:
                    await AuditService.record(
                        db,
                        OidcAuditEvent.GRANT_REVOKED,
                        'success',
                        client_id=client_id,
                        user_id=user_id,
                        grant_id=grant_id,
                        detail={'actor': actor, 'reason': reason},
                    )
                count += len(revoked)
            await db.commit()
            return count
        except Exception as exc:
            await db.rollback()
            raise ServiceException(message='批量撤销 Grant 失败') from exc

    @staticmethod
    async def set_access(db: AsyncSession, user_id: int, client_id: str, blocked: bool, actor: str, reason: str) -> int:
        """
        更新用户对应用的访问策略，禁止时撤销全部授权，解除时保留撤销状态

        :param db: 异步数据库会话
        :param user_id: 用户编号
        :param client_id: Client 公开标识
        :param blocked: 是否禁止访问
        :param actor: 操作人标识
        :param reason: 操作原因
        :return: 本次撤销的授权数量
        :raises ServiceException: 用户或应用不存在，或事务失败
        """

        try:
            client = await OAuthClientDao.get_by_client_id(db, client_id)
            user = await IdentityUserDao.get_user(db, user_id)
            if client is None or user is None or user.del_flag != '0':
                raise ServiceException(message='用户或应用不存在')
            await OAuthAccessPolicyDao.lock_client(db, client.client_pk)
            await OAuthAccessPolicyDao.set_status(db, user_id, client.client_pk, blocked, actor, reason)
            revoked = (
                await OAuthGrantDao.revoke_for_user_client(db, user_id, client.client_pk, reason) if blocked else []
            )
            for grant_id in revoked:
                await AuditService.record(
                    db,
                    OidcAuditEvent.GRANT_REVOKED,
                    'success',
                    client_id=client_id,
                    user_id=user_id,
                    grant_id=grant_id,
                    detail={'actor': actor, 'reason': reason},
                )
            await AuditService.record(
                db,
                OidcAuditEvent.CLIENT_ACCESS_BLOCKED if blocked else OidcAuditEvent.CLIENT_ACCESS_ALLOWED,
                'success',
                client_id=client_id,
                user_id=user_id,
                detail={'actor': actor, 'reason': reason},
            )
            await db.commit()
            return len(revoked)
        except ServiceException:
            await db.rollback()
            raise
        except Exception as exc:
            await db.rollback()
            raise ServiceException(message='更新用户应用访问策略失败') from exc
