from typing import Annotated

from fastapi import Form, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.aspect.db_session import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.constant import ApiNamespace
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import PageResponseModel
from module_identity.entity.vo.oauth_session_vo import AuditModel, AuditPageQueryModel
from module_identity.service.audit_service import AuditService
from utils.common_util import bytes2file_response
from utils.response_util import ResponseUtil

oauth_audit_controller = APIRouterPro(
    prefix='/monitor/oauth/audit', order_num=25, tags=['监控管理-OAuth 审计'], dependencies=[PreAuthDependency()]
)


@oauth_audit_controller.get(
    '/list',
    summary='获取 OAuth 审计分页列表接口',
    description='用于获取 OAuth 审计分页列表',
    response_model=PageResponseModel[AuditModel],
    dependencies=[UserInterfaceAuthDependency('monitor:oauthAudit:list')],
)
async def list_oauth_audit(
    query: Annotated[AuditPageQueryModel, Query()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    rows, total = await AuditService.list_admin_page(query_db, query)
    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_audit_controller.post(
    '/export',
    summary='导出 OAuth 审计接口',
    description='用于导出 OAuth 审计数据',
    response_class=StreamingResponse,
    dependencies=[UserInterfaceAuthDependency('monitor:oauthAudit:export')],
)
@ApiRateLimit(namespace=ApiNamespace.MONITOR_OAUTH_AUDIT_EXPORT, preset=ApiRateLimitPreset.USER_RESOURCE_EXPORT)
@Log(title='OAuth 审计', business_type=BusinessType.EXPORT)
async def export_oauth_audit(
    query: Annotated[AuditPageQueryModel, Form()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    data = await AuditService.export_admin(query_db, query)
    return ResponseUtil.streaming(
        data=bytes2file_response(data),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="oauth-audit.xlsx"'},
    )
