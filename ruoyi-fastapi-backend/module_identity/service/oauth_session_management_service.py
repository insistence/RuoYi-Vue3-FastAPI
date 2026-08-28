from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from exceptions.exception import ServiceException
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysSsoSession
from module_identity.entity.vo.oauth_session_vo import (
    GrantModel,
    GrantPageQueryModel,
    SessionPageQueryModel,
    SsoSessionModel,
)
from module_identity.service.audit_service import AuditService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.session_service import SsoSessionService


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
            status=row.status,
            revoked_at=getattr(row, 'revoked_at', None),
            revoke_reason=getattr(row, 'revoke_reason', None),
            create_time=getattr(row, 'create_time', None),
        )

    @staticmethod
    def grant_view(row: SysOAuthGrant, client_id: str | None) -> GrantModel:
        """
        将 OAuth Grant ORM 记录转换为 GrantModel

        :param row: OAuth Grant ORM 记录
        :param client_id: 客户端标识
        :return: Grant 管理视图
        """
        return GrantModel(
            grant_id=row.grant_id,
            user_id=row.user_id,
            subject_id=row.subject_id,
            client_id=client_id or '',
            granted_scopes=list(row.granted_scopes or []),
            granted_resources=list(row.granted_resources or []),
            status=row.status,
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
        return [OAuthSessionManagementService.session_view(row) for row in rows], total

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
            offset=(query.page_num - 1) * query.page_size,
            limit=query.page_size,
        )
        total = await OAuthGrantDao.count(db, user_id=query.user_id, client_id=query.client_id, status=query.status)
        keys = {int(row.client_pk) for row in rows}
        mapping = await OAuthClientDao.id_map(db, list(keys))
        return [OAuthSessionManagementService.grant_view(row, mapping.get(int(row.client_pk))) for row in rows], total

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
        return OAuthSessionManagementService.grant_view(row, client_id)

    @staticmethod
    async def revoke_user(db: AsyncSession, redis: Redis, user_id: int, actor: str, reason: str) -> int:
        """
        撤销用户全部有效 SSO Session

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
        按 grant_id 集合撤销 OAuth Grant

        :param db: 异步数据库会话
        :param grant_ids: 待撤销的 Grant 标识集合
        :param actor: 操作人标识
        :param reason: 撤销原因
        :return: 实际撤销的 Grant 数量
        :raises ServiceException: 批量撤销 Grant 事务失败
        """
        try:
            count = 0
            for grant_id in grant_ids:
                count += int(await OAuthGrantDao.revoke(db, grant_id, reason=reason))
                await AuditService.record(
                    db,
                    OidcAuditEvent.GRANT_REVOKED,
                    'success',
                    grant_id=grant_id,
                    detail={'actor': actor, 'reason': reason},
                )
            await db.commit()
            return count
        except Exception as exc:
            await db.rollback()
            raise ServiceException(message='批量撤销 Grant 失败') from exc
