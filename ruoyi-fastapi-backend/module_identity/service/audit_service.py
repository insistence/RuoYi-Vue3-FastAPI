import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.constant import OidcAuditEvent
from config.database import DataSourceRegistry
from exceptions.exception import OidcInteractionException
from module_identity.dao.oauth_audit_dao import OAuthAuditDao
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.vo.oauth_session_vo import AuditModel, AuditPageQueryModel
from utils.common_util import export_list2excel


class AuditService:
    """
    认证审计模块服务层
    """

    EVENT_FIELDS = frozenset(
        {
            'trace_id',
            'event_type',
            'result',
            'risk_level',
            'client_id',
            'resource_id',
            'user_id',
            'subject_id',
            'sid',
            'grant_id',
            'token_id',
            'ip_address',
            'user_agent',
            'failure_code',
            'detail',
            'create_time',
        }
    )
    HIGH_RISK_EVENTS = frozenset(
        {
            OidcAuditEvent.IDENTITY_SUBJECT_MISSING,
            OidcAuditEvent.AUTHORIZATION_CODE_REUSED,
            OidcAuditEvent.REFRESH_REUSE_DETECTED,
            OidcAuditEvent.CLIENT_SECRET_ROTATED,
            OidcAuditEvent.SIGNING_KEY_ROTATED,
            OidcAuditEvent.SESSION_REVOKED,
            OidcAuditEvent.TOKEN_REVOKED,
            OidcAuditEvent.TOKEN_FAILED,
            OidcAuditEvent.SECURITY_VERSION_CHANGED,
            OidcAuditEvent.INVALID_CLIENT,
            OidcAuditEvent.RESOURCE_POLICY_CHANGED,
            OidcAuditEvent.SCOPE_POLICY_CHANGED,
        }
    )
    _SENSITIVE_KEY = re.compile(
        r'(?:token|code|secret|cookie|password|passwd|credential|authorization|private[_-]?key|'
        r'pkce|verifier|nonce|client[_-]?assertion|assertion|access[_-]?token|refresh[_-]?token|'
        r'id[_-]?token|state)',
        re.IGNORECASE,
    )
    _SENSITIVE_VALUE = re.compile(
        r'(?i)(?:bearer\s+|basic\s+|(?:access|refresh|id)?[_-]?(?:token|secret|code|cookie|password|verifier)\s*[=:])'
    )
    _OPAQUE_CAPABILITY = re.compile(
        r'(?i)(?<![A-Za-z0-9_-])(?:'
        r'(?:rt1|ac1|ss1)\.[^.\s]{1,256}\.[^.\s]{1,4096}|'
        r'cs1\.[^.\s]{16,4096}(?:\.[^.\s]{1,256})?'
        r')(?![A-Za-z0-9_-])'
    )
    _JWT_PART_COUNT = 3
    _JWT_PART_MIN_LENGTH = 16
    _JWT_PART_MAX_LENGTH = 4096
    _EVENT_TYPE_MAX_LENGTH = 64

    @classmethod
    def sanitize_detail(cls, detail: Any) -> Any:
        """
        递归删除审计详情中的敏感字段

        :param detail: 待记录的任意可序列化值
        :return: 只包含安全字段的可序列化值
        """

        if isinstance(detail, Mapping):
            return {
                str(key): cls.sanitize_detail(value)
                for key, value in detail.items()
                if not cls._SENSITIVE_KEY.search(str(key))
            }
        if isinstance(detail, list):
            return [cls.sanitize_detail(value) for value in detail]
        if isinstance(detail, tuple):
            return [cls.sanitize_detail(value) for value in detail]
        if isinstance(detail, str):
            if (
                cls._SENSITIVE_VALUE.search(detail)
                or cls._looks_like_jwt(detail)
                or cls._OPAQUE_CAPABILITY.search(detail)
            ):
                return '[REDACTED]'
            return detail[:1024]
        if isinstance(detail, (int, float, bool)) or detail is None:
            return detail
        return None

    @staticmethod
    def _looks_like_jwt(value: str) -> bool:
        """
        判断字符串是否具有 JWT 三段式秘密外观

        :param value: 待检测的字符串
        :return: 是否符合 JWT 外形
        """

        parts = value.split('.')

        return len(parts) == AuditService._JWT_PART_COUNT and all(
            AuditService._JWT_PART_MIN_LENGTH <= len(part) <= AuditService._JWT_PART_MAX_LENGTH for part in parts
        )

    @classmethod
    def _risk_level(cls, event_type: str, risk_level: str | None) -> str:
        """
        计算事件风险等级

        :param event_type: 审计事件类型
        :param risk_level: 风险等级
        :return: 审计风险等级
        """

        if event_type in cls.HIGH_RISK_EVENTS:
            return 'high'
        return risk_level if risk_level in {'normal', 'medium', 'high', 'critical'} else 'normal'

    @classmethod
    def build_event(cls, **fields: Any) -> SysOAuthAuditLog:
        """
        按审计模型字段白名单构建安全事件对象

        :param fields: 审计字段；白名单以外的字段会被丢弃
        :return: 未提交的审计日志实体
        :raises ValueError: 缺少事件类型或结果时抛出
        """

        event_type = fields.get('event_type')
        result = fields.get('result')
        if (
            not isinstance(event_type, str)
            or not event_type.strip()
            or len(event_type.strip()) > cls._EVENT_TYPE_MAX_LENGTH
        ):
            raise ValueError('event_type must be 1-64 characters')
        if result not in {'success', 'failure'}:
            raise ValueError('result is required')
        values = {key: value for key, value in fields.items() if key in cls.EVENT_FIELDS}
        values['event_type'] = event_type.strip()
        values['result'] = result.strip()
        values['risk_level'] = cls._risk_level(values['event_type'], values.get('risk_level'))
        if 'detail' in values:
            values['detail'] = cls.sanitize_detail(values['detail'])
        for field, limit in (
            ('trace_id', 64),
            ('client_id', 64),
            ('resource_id', 64),
            ('subject_id', 36),
            ('sid', 36),
            ('grant_id', 36),
            ('token_id', 36),
            ('ip_address', 128),
            ('user_agent', 500),
            ('failure_code', 64),
        ):
            if isinstance(values.get(field), str):
                safe_value = cls.sanitize_detail(values[field]) if field == 'user_agent' else values[field]
                values[field] = safe_value[:limit] if isinstance(safe_value, str) else None
        return SysOAuthAuditLog(**values)

    @classmethod
    async def record(
        cls,
        db: AsyncSession,
        event_type: str,
        result: str,
        *,
        risk_level: str = 'normal',
        **fields: Any,
    ) -> SysOAuthAuditLog:
        """
        脱敏并追加一条审计事件，不提交调用方事务

        :param db: 异步数据库会话
        :param event_type: 事件类型
        :param result: 事件结果
        :param risk_level: 调用方建议的风险等级
        :param fields: 其余白名单审计字段
        :return: 已刷新但尚未提交的审计日志实体
        """

        event = cls.build_event(event_type=event_type, result=result, risk_level=risk_level, **fields)

        return await OAuthAuditDao.append(db, event)

    @classmethod
    async def record_independent(
        cls,
        db: AsyncSession,
        event_type: str,
        result: str,
        *,
        risk_level: str = 'normal',
        **fields: Any,
    ) -> SysOAuthAuditLog:
        """
        在不依赖业务事务的独立会话中提交审计事件

        :param db: 当前业务会话，用于测试环境复用其绑定引擎
        :param event_type: 事件类型
        :param result: 结果
        :param risk_level: 风险等级
        :param fields: 经过白名单过滤的安全字段
        :return: 已提交的审计日志实体
        """

        engine = db.info.get('service_engine') or getattr(db, 'bind', None)
        if engine is not None:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as audit_db:
                event = await cls.record(
                    audit_db,
                    event_type,
                    result,
                    risk_level=risk_level,
                    **fields,
                )
                await audit_db.commit()
                return event
        async with DataSourceRegistry.session() as audit_db:
            event = await cls.record(
                audit_db,
                event_type,
                result,
                risk_level=risk_level,
                **fields,
            )
            await audit_db.commit()
            return event

    @classmethod
    async def append(cls, db: AsyncSession, event: SysOAuthAuditLog | Mapping[str, Any]) -> SysOAuthAuditLog:
        """
        追加事件对象或字段映射，并保留调用方提交边界

        :param db: 异步数据库会话
        :param event: 审计实体或待构建字段映射
        :return: 已刷新但尚未提交的审计日志实体
        """

        row = event if isinstance(event, SysOAuthAuditLog) else cls.build_event(**dict(event))

        return await OAuthAuditDao.append(db, row)

    @staticmethod
    def _admin_filters(query: AuditPageQueryModel) -> dict[str, object]:
        """
        构造管理端审计查询条件

        :param query: 管理端审计分页查询条件
        :return: 传给审计 DAO 的筛选条件
        """

        return {
            'client_id': query.client_id,
            'user_id': query.user_id,
            'event_type': query.event_type,
            'result': query.result,
            'risk_level': query.risk_level,
            'start_time': query.start_time,
            'end_time': query.end_time,
        }

    @staticmethod
    def _admin_model(row: SysOAuthAuditLog) -> dict[str, object]:
        """
        将审计实体投影为脱敏管理端模型

        :param row: 审计日志实体
        :return: 不含详情敏感字段的管理端模型字典
        """

        return AuditModel(
            audit_id=row.event_id,
            event_type=row.event_type,
            result=row.result,
            risk_level=row.risk_level,
            trace_id=getattr(row, 'trace_id', None),
            client_id=getattr(row, 'client_id', None),
            resource_id=getattr(row, 'resource_id', None),
            user_id=getattr(row, 'user_id', None),
            subject_id=getattr(row, 'subject_id', None),
            sid=getattr(row, 'sid', None),
            ip_address=getattr(row, 'ip_address', None),
            failure_code=getattr(row, 'failure_code', None),
            create_time=row.create_time,
        ).model_dump(by_alias=True)

    @classmethod
    async def list_admin_page(cls, db: AsyncSession, query: AuditPageQueryModel) -> tuple[list[dict[str, object]], int]:
        """
        查询管理端审计分页并返回脱敏结果

        :param db: 异步数据库会话
        :param query: 管理端审计分页查询条件
        :return: 脱敏审计行列表及总数
        """

        params = cls._admin_filters(query)
        rows = await OAuthAuditDao.list_admin_page(
            db, offset=(query.page_num - 1) * query.page_size, limit=query.page_size, **params
        )
        total = await OAuthAuditDao.count_admin(db, **params)

        return [cls._admin_model(row) for row in rows], total

    @classmethod
    async def export_admin(cls, db: AsyncSession, query: AuditPageQueryModel) -> bytes:
        """
        导出管理端审计分页范围内的脱敏数据

        :param db: 异步数据库会话
        :param query: 管理端审计筛选条件
        :return: 脱敏审计 Excel 文件字节
        """

        rows = await OAuthAuditDao.list_admin_page(db, offset=0, limit=5000, **cls._admin_filters(query))

        return export_list2excel([cls._admin_model(row) for row in rows])

    @classmethod
    async def record_interaction_failure(cls, db: AsyncSession, event_type: str, **fields: Any) -> None:
        """
        回滚交互事务并独立提交高风险失败审计

        :param db: 认证交互使用的异步数据库会话
        :param event_type: 失败审计事件类型
        :param fields: 经过白名单过滤的审计字段
        :return: None
        :raises OidcInteractionException: 独立审计提交失败时抛出
        """

        await db.rollback()
        try:
            await cls.record_independent(db, event_type, 'failure', risk_level='high', **fields)
        except Exception as exc:
            await db.rollback()
            raise OidcInteractionException(error='server_error', status_code=503, message='认证审计服务不可用') from exc

    @staticmethod
    def interaction_subject_writer(db: AsyncSession) -> Callable[[int], Awaitable[object]]:
        """
        构造缺失身份主体的独立审计写入器

        :param db: 认证交互使用的异步数据库会话
        :return: 接收用户 ID 并独立写入审计的异步回调
        """

        async def write(user_id: int) -> object:
            """
            写入审计记录

            :param user_id: 本地用户 ID
            :return: 已提交的审计日志实体
            """

            return await AuditService.record_independent(
                db,
                OidcAuditEvent.IDENTITY_SUBJECT_MISSING,
                'failure',
                risk_level='high',
                user_id=user_id if isinstance(user_id, int) else None,
                failure_code='identity_integrity',
            )

        return write
