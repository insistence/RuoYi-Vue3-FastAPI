from collections.abc import Iterable
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException, OidcInteractionException
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao, OAuthGrantSnapshot
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant
from module_identity.entity.vo.interaction_vo import InteractionConsentModel, InteractionResultModel
from module_identity.service.audit_service import AuditService
from module_identity.service.authorization_service import (
    AuthorizationContext,
    AuthorizationService,
    ClientSnapshot,
    ResourceSnapshot,
    ScopeSnapshot,
)
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.interaction_service import InteractionFlowService


@dataclass(frozen=True, slots=True)
class ConsentResult:
    """
    授权确认结果

    :ivar approved: 是否批准授权
    :ivar scopes: 服务端从原请求范围内收敛后的 Scope
    :ivar grant: 本次同意关联的可撤销 Grant
    """

    approved: bool
    scopes: tuple[str, ...]
    grant: SysOAuthGrant | None = None
    previous_grant: OAuthGrantSnapshot | None = None
    persisted_grant: OAuthGrantSnapshot | None = None


class ConsentService:
    """
    授权同意模块服务层

    用户提交只能取消原始请求中的可选 Scope，不能增加 Scope，也不能取消服务端必需 Scope
    每次同意均保存可撤销 Grant，记住同意仅控制后续是否需要再次确认
    """

    @staticmethod
    def validate_submission(context: AuthorizationContext, approved: bool, scopes: Iterable[str]) -> tuple[str, ...]:
        """
        校验并收敛用户提交的授权 Scope

        :param context: 已完成协议校验的授权上下文
        :param approved: 用户是否批准授权
        :param scopes: 用户提交的 Scope 集合
        :return: 按原请求顺序返回的有效 Scope
        :raises OAuthProtocolException: 拒绝授权、扩大 Scope 或取消必需 Scope 时抛出
        """

        requested = tuple(context.scopes)
        submitted = tuple(dict.fromkeys(scopes))
        requested_set = set(requested)
        submitted_set = set(submitted)
        if not approved:
            raise ConsentService._redirect_error(context, 'access_denied', 'User denied the authorization request')
        if not submitted_set.issubset(requested_set):
            raise ConsentService._redirect_error(context, 'invalid_scope', 'Submitted scope is not allowed')
        if not set(context.required_scopes).issubset(submitted_set):
            raise ConsentService._redirect_error(context, 'invalid_scope', 'Required scope cannot be removed')
        return tuple(scope for scope in requested if scope in submitted_set)

    @classmethod
    async def remember_consent(
        cls,
        db: AsyncSession,
        context: AuthorizationContext,
        user_id: int,
        subject_id: str,
        scopes: Iterable[str],
    ) -> SysOAuthGrant:
        """
        持久化用户同意的 Scope

        :param db: 异步数据库会话
        :param context: 已完成协议校验的授权上下文
        :param user_id: 本地用户 ID
        :param subject_id: 稳定 OIDC Subject
        :param scopes: 已通过校验的 Scope 集合
        :return: 新建或合并后的 Grant

        调用方负责提交事务；本方法不执行 commit。Grant 撤销与 Token 联动不在本接口内完成
        """

        selected_scopes = cls.validate_submission(context, True, scopes)

        return await OAuthGrantDao.merge_active_grant(
            db=db,
            user_id=user_id,
            subject_id=subject_id,
            client_pk=context.client.client_pk,
            granted_scopes=list(selected_scopes),
            granted_resources=list(context.resources),
            client_policy_version=context.client.policy_version,
        )

    @classmethod
    async def submit_consent(
        cls,
        db: AsyncSession,
        context: AuthorizationContext,
        approved: bool,
        scopes: Iterable[str],
        remember_consent: bool = False,
        user_id: int | None = None,
        subject_id: str | None = None,
    ) -> ConsentResult:
        """
        处理授权确认并写入可撤销 Grant

        :param db: 异步数据库会话
        :param context: 已完成协议校验的授权上下文
        :param approved: 用户是否批准授权
        :param scopes: 用户提交的 Scope 集合
        :param remember_consent: 是否在后续请求复用本次同意，不影响授权记录的保存
        :param user_id: 持久化 Grant 所需的本地用户 ID
        :param subject_id: 持久化 Grant 所需的稳定 Subject
        :return: 授权处理结果

        调用方负责 commit；拒绝授权不会写入 Grant
        """

        selected_scopes = cls.validate_submission(context, approved, scopes)
        if user_id is None or subject_id is None:
            raise ValueError('创建授权记录必须提供用户编号和主体标识')
        await OAuthAccessPolicyDao.lock_client(db, context.client.client_pk)
        if await OAuthAccessPolicyDao.is_blocked(db, user_id, context.client.client_pk, for_update=True):
            raise OAuthProtocolException('access_denied', 'Access to this application is blocked')
        current = await OAuthGrantDao.get_active_for_user_client(db, user_id, context.client.client_pk, for_update=True)
        previous_grant = OAuthGrantDao.snapshot(current) if current is not None else None
        grant = await OAuthGrantDao.merge_active_grant(
            db=db,
            user_id=user_id,
            subject_id=subject_id,
            client_pk=context.client.client_pk,
            granted_scopes=list(selected_scopes),
            granted_resources=list(context.resources),
            client_policy_version=context.client.policy_version,
            remember_consent=remember_consent,
        )
        return ConsentResult(
            approved=True,
            scopes=selected_scopes,
            grant=grant,
            previous_grant=previous_grant,
            persisted_grant=OAuthGrantDao.snapshot(grant) if grant is not None else None,
        )

    @staticmethod
    async def compensate_persisted_grant(db: AsyncSession, result: ConsentResult) -> None:
        """
        补偿已提交但 Interaction CAS 失败的持久授权

        :param db: 用于独立补偿事务的数据库会话
        :param result: 已提交的授权结果及更新前快照
        :return: None
        """

        if result.grant is None or result.persisted_grant is None:
            return
        try:
            if result.previous_grant is None:
                restored = await OAuthGrantDao.revoke_snapshot(
                    db,
                    result.persisted_grant,
                    reason='interaction_transition_failed',
                )
            else:
                restored = await OAuthGrantDao.restore_snapshot(
                    db,
                    result.previous_grant,
                    result.persisted_grant,
                )
            if restored:
                await db.commit()
                return
            await db.rollback()
            await AuditService.record_independent(
                db,
                OidcAuditEvent.CONSENT_GRANTED,
                'failure',
                risk_level='high',
                user_id=result.persisted_grant.user_id,
                subject_id=result.persisted_grant.subject_id,
                grant_id=result.persisted_grant.grant_id,
                failure_code='consent_compensation_conflict',
                detail={'reason': 'grant_changed_after_interaction_commit'},
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def consent_is_satisfied(context: AuthorizationContext, grant: SysOAuthGrant | None) -> bool:
        """
        判断已有 Grant 是否可以跳过本次同意页

        :param context: 已完成协议校验的授权上下文
        :param grant: 当前用户和 Client 的候选 Grant
        :return: 仅当策略版本、范围和 Resource 均匹配时返回 True
        """

        return AuthorizationService.consent_is_satisfied(context, grant)

    @staticmethod
    def _redirect_error(context: AuthorizationContext, error: str, description: str) -> OAuthProtocolException:
        """
        创建带已验证 Redirect 的授权错误

        :param context: 已完成 Redirect 校验的上下文
        :param error: OAuth 标准错误码
        :param description: 安全错误描述
        :return: 可安全重定向的协议异常
        """

        return OAuthProtocolException(
            error,
            description,
            400,
            redirect_uri=context.redirect_uri,
            state=context.state,
            redirect_uri_verified=True,
            issuer=OidcConfig.oidc_issuer,
        )


class InteractionConsentService:
    """
    认证中心授权同意流程模块服务层
    """

    @staticmethod
    async def context_from_record(db: AsyncSession, record: dict[str, object]) -> AuthorizationContext:
        """
        从 Interaction 白名单记录和当前数据库策略重建同意上下文

        :param db: 异步数据库会话
        :param record: Interaction 内部记录
        :return: 当前策略下的授权上下文
        """

        client = await OAuthClientDao.get_by_pk(db, record['clientPk'], active_only=True)
        if client is None:
            raise OidcInteractionException(
                record['interactionId'], '客户端已停用或不可用', error='invalid_request', status_code=409
            )
        bindings = await OAuthClientDao.list_scope_bindings(db, client.client_pk)
        scopes = await AuthorizationService.load_scope_models(db, bindings)
        by_code = {scope.scope_code: scope for scope in scopes if scope.status == '0'}
        requested = tuple(record['scopes'])
        if any(scope not in by_code for scope in requested):
            raise OidcInteractionException(
                record['interactionId'], '权限范围策略已变更，请重新授权', error='invalid_scope'
            )
        requested_resources = tuple(record['resources'])
        resource_rows = await OAuthClientDao.list_resources(db, client.client_pk)
        resource = next((item for item in resource_rows if item.audience in requested_resources), None)
        if requested_resources and resource is None:
            raise OidcInteractionException(
                record['interactionId'], '资源访问策略已变更，请重新授权', error='invalid_scope', status_code=409
            )
        required = frozenset({'openid'} | {code for code in requested if not bool(by_code[code].consent_required)})
        pre_authorized = frozenset(
            code
            for code in requested
            for binding in bindings
            if binding.scope_pk == by_code[code].scope_pk and bool(binding.pre_authorized)
        )

        return AuthorizationContext(
            client=ClientSnapshot(
                client_pk=client.client_pk,
                client_id=client.client_id,
                policy_version=client.policy_version,
                grant_types=tuple(client.grant_types or ()),
                response_types=tuple(client.response_types or ()),
                require_pkce=bool(client.require_pkce),
                require_consent=bool(client.require_consent),
                trusted_client=bool(client.trusted_client),
            ),
            redirect_uri=record['redirectUri'],
            scopes=requested,
            scope_models=tuple(
                ScopeSnapshot(
                    scope_pk=by_code[code].scope_pk,
                    scope_code=code,
                    scope_type=by_code[code].scope_type,
                    resource_pk=by_code[code].resource_pk,
                    consent_required=bool(by_code[code].consent_required),
                )
                for code in requested
            ),
            pre_authorized_scopes=pre_authorized,
            resource=ResourceSnapshot(resource.resource_pk, resource.audience) if resource is not None else None,
            state=record.get('state'),
            nonce=record['nonce'],
            code_challenge=record['codeChallenge'],
            code_challenge_method=record['codeChallengeMethod'],
            prompt=' '.join(record.get('prompt') or ()),
            max_age=record.get('maxAge'),
            required_scopes=required,
        )

    @staticmethod
    async def consent(
        redis: Redis,
        interaction_id: str,
        body: InteractionConsentModel,
        db: AsyncSession,
        csrf_token: str | None,
    ) -> InteractionResultModel:
        """
        校验并提交授权同意，只允许原始 Scope 子集

        :param redis: 交互 Redis
        :param interaction_id: Interaction 标识
        :param body: 同意状态和 Scope 参数
        :param db: 异步数据库会话
        :param csrf_token: Interaction CSRF 原文
        :return: 同源完成跳转动作
        """

        record = await InteractionFlowService.csrf_record(redis, interaction_id, csrf_token)
        InteractionFlowService.require_status(record, 'awaiting_consent')
        context = await InteractionConsentService.context_from_record(db, record)
        try:
            result = await ConsentService.submit_consent(
                db,
                context,
                body.approved,
                body.scopes,
                body.remember_consent,
                user_id=record.get('userId'),
                subject_id=record.get('subjectId'),
            )
        except OAuthProtocolException as exc:
            if exc.error != 'access_denied':
                await AuditService.record_interaction_failure(
                    db,
                    OidcAuditEvent.AUTHORIZE_DENIED,
                    client_id=record.get('clientId'),
                    user_id=record.get('userId'),
                    failure_code=exc.error,
                )
                raise
            await AuditService.record(
                db,
                OidcAuditEvent.AUTHORIZE_DENIED,
                'success',
                client_id=record.get('clientId'),
                user_id=record.get('userId'),
                subject_id=str(record.get('subjectId')) if record.get('subjectId') else None,
                failure_code='access_denied',
            )
            await InteractionFlowService.commit_transition(
                db, AfterCommitCoordinator(), redis, interaction_id, 'denied'
            )
            return InteractionFlowService.interaction_result(interaction_id, 'redirect')

        grant_id = result.grant.grant_id if result.grant is not None else record.get('grantId')
        await AuditService.record(
            db,
            OidcAuditEvent.CONSENT_GRANTED,
            'success',
            client_id=record.get('clientId'),
            user_id=record.get('userId'),
            subject_id=str(record.get('subjectId')) if record.get('subjectId') else None,
            grant_id=grant_id,
        )

        async def compensate() -> None:
            """
            执行事务补偿

            :return: None
            """

            await ConsentService.compensate_persisted_grant(db, result)

        await InteractionFlowService.commit_transition(
            db,
            AfterCommitCoordinator(),
            redis,
            interaction_id,
            'completed',
            {'scopes': list(result.scopes), 'grantId': grant_id},
            compensate=compensate if result.grant is not None else None,
        )

        return InteractionFlowService.interaction_result(interaction_id, 'redirect')

    @staticmethod
    async def cancel(
        redis: Redis,
        interaction_id: str,
        db: AsyncSession,
        csrf_token: str | None,
    ) -> InteractionResultModel:
        """
        以 CSRF 保护的原子状态迁移拒绝当前授权

        :param redis: 交互 Redis
        :param interaction_id: Interaction 标识
        :param db: 异步数据库会话
        :param csrf_token: Interaction CSRF 原文
        :return: 同源完成跳转动作
        """

        record = await InteractionFlowService.csrf_record(redis, interaction_id, csrf_token)
        if record.get('status') not in {'awaiting_login', 'awaiting_consent', 'password_change_required'}:
            raise OidcInteractionException(
                interaction_id, '认证交互已失效，请重新发起认证', error='invalid_request', status_code=409
            )
        await AuditService.record(
            db,
            OidcAuditEvent.AUTHORIZE_DENIED,
            'success',
            client_id=record.get('clientId'),
            user_id=record.get('userId'),
            failure_code='access_denied',
        )
        await InteractionFlowService.commit_transition(db, AfterCommitCoordinator(), redis, interaction_id, 'denied')

        return InteractionFlowService.interaction_result(interaction_id, 'redirect')
