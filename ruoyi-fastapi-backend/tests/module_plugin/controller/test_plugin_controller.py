import json
from collections.abc import Generator
from datetime import datetime
from types import SimpleNamespace

import pytest

from common.annotation import log_annotation
from common.context import RequestContext
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_plugin.controller import plugin_controller
from plugins.core.management.entity.vo.schemas import (
    PluginBatchActionModel,
    PluginOperationLogDetailModel,
    PluginOperationLogExportQueryModel,
    PluginOperationLogPageQueryModel,
    PluginOperationLogRetentionModel,
    PluginOperationLogRetentionResultModel,
)

HTTP_OK = 200
EXPECTED_RETENTION_MATCHED_COUNT = 2
PLUGIN_OPERATION_FAILURE_EXIT_CODE = 10


def build_request(path: str = '/system/plugin/batch', method: str = 'POST') -> object:
    """构造测试用请求对象。"""

    async def empty_body() -> bytes:
        """返回测试用空请求体。"""
        return b''

    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        method=method,
        headers={'User-Agent': 'pytest'},
        client=SimpleNamespace(host='127.0.0.1'),
        query_params={},
        path_params={},
        body=empty_body,
    )


def load_response_body(response: object) -> dict:
    """解析测试响应体。"""
    return json.loads(response.body.decode())


def test_plugin_operation_response_hides_exit_code_from_web_payload() -> None:
    """校验 Web 插件操作响应不会暴露 CLI 退出码。"""
    payload = {
        'ok': True,
        'message': '插件操作完成',
        'pluginId': 'demo',
        'exit_code': PLUGIN_OPERATION_FAILURE_EXIT_CODE,
    }

    response = plugin_controller._plugin_operation_response(payload, '插件操作完成')
    body = load_response_body(response)

    assert body['success'] is True
    assert body['data']['pluginId'] == 'demo'
    assert 'exit_code' not in body['data']
    assert payload['exit_code'] == PLUGIN_OPERATION_FAILURE_EXIT_CODE


class FakeAsyncSession:
    """
    测试用异步数据库会话。
    """

    def __init__(self) -> None:
        """初始化测试会话。"""
        self.committed = False

    async def commit(self) -> None:
        """记录事务提交。"""
        self.committed = True


@pytest.fixture(autouse=True)
def fake_request_context(monkeypatch: pytest.MonkeyPatch) -> Generator[CurrentUserModel, None, None]:
    """构造日志装饰器所需的最小请求上下文。"""
    user = CurrentUserModel(
        permissions=['*:*:*'],
        roles=[],
        user=UserInfoModel(userName='admin', dept=None, role=[]),
    )
    user_token = RequestContext.set_current_user(user)
    pattern_token = RequestContext.set_current_exclude_patterns([])

    async def fake_enqueue_operation_log(*args: object, **kwargs: object) -> None:
        """记录测试中的操作日志入队请求。"""

    monkeypatch.setattr(log_annotation.LogQueueService, 'enqueue_operation_log', fake_enqueue_operation_log)
    try:
        yield user
    finally:
        RequestContext.reset_current_user(user_token)
        RequestContext.reset_current_exclude_patterns(pattern_token)


@pytest.mark.asyncio
async def test_batch_system_plugins_accepts_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验批量操作接口使用 JSON 请求体。"""
    recorded: dict[str, object] = {}

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        async def batch_plugins(
            self,
            operation: str,
            plugin_ids: list[str] | None = None,
            *,
            dry_run: bool = True,
            continue_on_error: bool = False,
        ) -> dict[str, object]:
            """记录批量操作参数。"""
            recorded.update(
                {
                    'operation': operation,
                    'plugin_ids': plugin_ids,
                    'dry_run': dry_run,
                    'continue_on_error': continue_on_error,
                }
            )
            return {'ok': True, 'message': '批量操作完成'}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.batch_system_plugins(
        request=build_request('/system/plugin/batch'),
        batch_action=PluginBatchActionModel(
            operation='install',
            dryRun=True,
            continueOnError=True,
            pluginIds=['demo', 'ai'],
        ),
    )

    assert response.status_code == HTTP_OK
    assert recorded == {
        'operation': 'install',
        'plugin_ids': ['demo', 'ai'],
        'dry_run': True,
        'continue_on_error': True,
    }


@pytest.mark.asyncio
async def test_install_system_plugin_accepts_dry_run_query_param(
    monkeypatch: pytest.MonkeyPatch,
    fake_request_context: CurrentUserModel,
) -> None:
    """校验单插件安装接口使用展开后的 dryRun 查询参数。"""
    recorded: dict[str, object] = {}

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        async def install_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            operated_by: str | None = None,
        ) -> dict[str, object]:
            """记录安装参数。"""
            recorded.update({'plugin_id': plugin_id, 'dry_run': dry_run})
            return {'ok': True, 'message': '安装完成'}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.install_system_plugin(
        request=build_request('/system/plugin/demo/install'),
        plugin_id='demo',
        current_user=fake_request_context,
        dry_run=True,
    )

    assert response.status_code == HTTP_OK
    assert recorded == {'plugin_id': 'demo', 'dry_run': True}


@pytest.mark.asyncio
async def test_install_system_plugin_returns_failure_when_runtime_payload_is_not_ok(
    monkeypatch: pytest.MonkeyPatch,
    fake_request_context: CurrentUserModel,
) -> None:
    """校验安装运行时返回失败时接口返回失败响应。"""

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        async def install_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            operated_by: str | None = None,
        ) -> dict[str, object]:
            """返回失败安装结果。"""
            return {'ok': False, 'message': '插件安装失败', 'pluginId': plugin_id}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.install_system_plugin(
        request=build_request('/system/plugin/demo/install'),
        plugin_id='demo',
        current_user=fake_request_context,
        dry_run=False,
    )
    body = load_response_body(response)

    assert response.status_code == HTTP_OK
    assert body['success'] is False
    assert body['msg'] == '插件安装失败'
    assert body['data']['ok'] is False


@pytest.mark.asyncio
async def test_install_system_plugin_dependencies_forces_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验 Web 依赖安装接口始终只生成 dry-run 安装计划。"""
    recorded: dict[str, object] = {}

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        def install_plugin_dependencies(
            self,
            plugin_id: str,
            *,
            dry_run: bool = True,
            policy_config: object | None = None,
        ) -> dict[str, object]:
            """记录依赖安装参数。"""
            recorded.update({'plugin_id': plugin_id, 'dry_run': dry_run, 'policy_mode': policy_config.mode})
            return {'ok': True, 'message': '插件依赖安装演练完成', 'pluginId': plugin_id}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.install_system_plugin_dependencies(
        request=build_request('/system/plugin/demo/dependencies/install'),
        plugin_id='demo',
        dry_run=False,
    )
    body = load_response_body(response)

    assert response.status_code == HTTP_OK
    assert body['success'] is True
    assert recorded == {'plugin_id': 'demo', 'dry_run': True, 'policy_mode': 'plan_only'}


@pytest.mark.asyncio
async def test_enable_system_plugin_returns_runtime_payload_when_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验启用插件失败时接口透传运行时失败负载。"""

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        async def set_plugin_enabled(self, plugin_id: str, *, enabled: bool, dry_run: bool = False) -> dict:
            """返回失败启用结果。"""
            return {'ok': False, 'message': '启用失败', 'pluginId': plugin_id, 'enabled': enabled}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.enable_system_plugin(
        request=build_request('/system/plugin/demo/enable', method='PUT'),
        plugin_id='demo',
        query_db=FakeAsyncSession(),
    )
    body = load_response_body(response)

    assert response.status_code == HTTP_OK
    assert body['success'] is False
    assert body['msg'] == '启用失败'
    assert body['data']['ok'] is False
    assert body['data']['pluginId'] == 'demo'


@pytest.mark.asyncio
async def test_disable_system_plugin_delegates_runtime_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验停用插件接口走运行时服务，确保内部事务会被提交。"""
    recorded: dict[str, object] = {}

    class FakePluginRuntimeService:
        """
        测试用插件运行时服务。
        """

        async def set_plugin_enabled(self, plugin_id: str, *, enabled: bool, dry_run: bool = False) -> dict:
            """记录插件启停参数。"""
            recorded.update({'plugin_id': plugin_id, 'enabled': enabled, 'dry_run': dry_run})
            return {'ok': True, 'message': '停用成功', 'pluginId': plugin_id, 'enabled': enabled}

    monkeypatch.setattr(plugin_controller, 'get_plugin_runtime_service', FakePluginRuntimeService)

    response = await plugin_controller.disable_system_plugin(
        request=build_request('/system/plugin/demo/disable', method='PUT'),
        plugin_id='demo',
    )
    body = load_response_body(response)

    assert response.status_code == HTTP_OK
    assert recorded == {'plugin_id': 'demo', 'enabled': False, 'dry_run': False}
    assert body['success'] is True
    assert body['msg'] == '停用成功'
    assert body['data']['pluginId'] == 'demo'
    assert body['data']['enabled'] is False


@pytest.mark.asyncio
async def test_get_system_plugin_operation_log_list_returns_page_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验审计列表接口会返回分页负载并透传查询条件。"""
    recorded: dict[str, object] = {}
    operation_log = PluginOperationLogDetailModel(
        operationId=1,
        operation='install',
        pluginIds=['demo'],
        dryRun=False,
        continueOnError=False,
        status='success',
        summary={'total': 1},
        result={'ok': True},
        remark='安装完成',
    )
    page_result = PageModel[PluginOperationLogDetailModel](
        rows=[operation_log],
        pageNum=1,
        pageSize=10,
        total=1,
        hasNext=False,
    )

    class FakePluginService:
        """
        测试用插件管理服务。
        """

        @classmethod
        async def get_plugin_operation_log_page_list_services(
            cls,
            query_db: object,
            query_object: PluginOperationLogPageQueryModel,
            is_page: bool = True,
        ) -> PageModel[PluginOperationLogDetailModel]:
            """记录审计列表查询参数。"""
            recorded.update(
                {
                    'query_db': query_db,
                    'plugin_id': query_object.plugin_id,
                    'operation': query_object.operation,
                    'status': query_object.status,
                    'is_page': is_page,
                }
            )
            return page_result

    monkeypatch.setattr(plugin_controller, 'PluginService', FakePluginService)
    query_db = FakeAsyncSession()

    response = await plugin_controller.get_system_plugin_operation_log_list(
        request=build_request('/system/plugin/operation-log/list', method='GET'),
        operation_log_page_query=PluginOperationLogPageQueryModel(
            pluginId='demo',
            operation='install',
            status='success',
            pageNum=1,
            pageSize=10,
        ),
        query_db=query_db,
    )

    body = load_response_body(response)
    assert response.status_code == HTTP_OK
    assert body['success'] is True
    assert body['total'] == 1
    assert body['rows'][0]['operationId'] == 1
    assert body['rows'][0]['pluginIds'] == ['demo']
    assert recorded == {
        'query_db': query_db,
        'plugin_id': 'demo',
        'operation': 'install',
        'status': 'success',
        'is_page': True,
    }


@pytest.mark.asyncio
async def test_query_detail_system_plugin_operation_log_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验审计详情接口会返回插件操作审计详情。"""
    recorded: dict[str, object] = {}
    operation_log = PluginOperationLogDetailModel(
        operationId=1,
        operation='install',
        pluginIds=['demo'],
        dryRun=False,
        continueOnError=False,
        status='success',
        summary={'total': 1},
        result={'ok': True},
        remark='安装完成',
    )

    class FakePluginService:
        """
        测试用插件管理服务。
        """

        @classmethod
        async def plugin_operation_log_detail_services(
            cls,
            query_db: object,
            operation_id: int,
        ) -> PluginOperationLogDetailModel:
            """记录审计详情查询参数。"""
            recorded.update({'query_db': query_db, 'operation_id': operation_id})
            return operation_log

    monkeypatch.setattr(plugin_controller, 'PluginService', FakePluginService)
    query_db = FakeAsyncSession()

    response = await plugin_controller.query_detail_system_plugin_operation_log(
        request=build_request('/system/plugin/operation-log/1', method='GET'),
        operation_id=1,
        query_db=query_db,
    )

    body = load_response_body(response)
    assert response.status_code == HTTP_OK
    assert body['success'] is True
    assert body['data']['operationId'] == 1
    assert body['data']['pluginIds'] == ['demo']
    assert recorded == {'query_db': query_db, 'operation_id': 1}


@pytest.mark.asyncio
async def test_query_detail_system_plugin_operation_log_returns_failure_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验审计详情不存在时返回失败响应。"""

    class FakePluginService:
        """
        测试用插件管理服务。
        """

        @classmethod
        async def plugin_operation_log_detail_services(cls, query_db: object, operation_id: int) -> None:
            """返回空审计详情。"""
            return

    monkeypatch.setattr(plugin_controller, 'PluginService', FakePluginService)

    response = await plugin_controller.query_detail_system_plugin_operation_log(
        request=build_request('/system/plugin/operation-log/404', method='GET'),
        operation_id=404,
        query_db=FakeAsyncSession(),
    )

    body = load_response_body(response)
    assert response.status_code == HTTP_OK
    assert body['success'] is False
    assert body['msg'] == '插件批量操作审计日志不存在'


@pytest.mark.asyncio
async def test_retain_system_plugin_operation_log_commits_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验审计保留策略接口会调用管理服务并提交事务。"""
    recorded: dict[str, object] = {}
    retention_result = PluginOperationLogRetentionResultModel(
        retentionDays=0,
        cutoffTime=datetime(2026, 5, 22, 12, 0, 0),
        matchedCount=2,
        deletedCount=0,
        dryRun=True,
    )

    class FakePluginService:
        """
        测试用插件管理服务。
        """

        @classmethod
        async def retain_plugin_operation_log_services(
            cls,
            query_db: object,
            retention_model: PluginOperationLogRetentionModel,
        ) -> PluginOperationLogRetentionResultModel:
            """记录审计保留策略调用参数。"""
            recorded.update({'query_db': query_db, 'retention_days': retention_model.retention_days})
            return retention_result

    monkeypatch.setattr(plugin_controller, 'PluginService', FakePluginService)
    query_db = FakeAsyncSession()

    response = await plugin_controller.retain_system_plugin_operation_log(
        request=build_request('/system/plugin/operation-log/retention', method='DELETE'),
        retention_query=PluginOperationLogRetentionModel(retentionDays=0, dryRun=True),
        query_db=query_db,
    )

    body = load_response_body(response)
    assert response.status_code == HTTP_OK
    assert body['success'] is True
    assert body['data']['retentionDays'] == 0
    assert body['data']['matchedCount'] == EXPECTED_RETENTION_MATCHED_COUNT
    assert query_db.committed is True
    assert recorded == {'query_db': query_db, 'retention_days': 0}


@pytest.mark.asyncio
async def test_export_system_plugin_operation_log_uses_operation_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验审计导出接口会使用操作类型字典映射。"""
    recorded: dict[str, object] = {}
    operation_log = PluginOperationLogDetailModel(
        operationId=1,
        operation='config_set',
        pluginIds=['demo'],
        dryRun=False,
        continueOnError=False,
        status='success',
        summary={},
        result={},
        remark='配置保存',
    )

    class FakePluginService:
        """
        测试用插件管理服务。
        """

        @classmethod
        async def get_plugin_operation_log_export_list_services(
            cls,
            query_db: object,
            query_object: PluginOperationLogExportQueryModel,
        ) -> list[PluginOperationLogDetailModel]:
            """记录审计导出查询参数。"""
            recorded.update({'query_db': query_db, 'export_limit': query_object.export_limit})
            return [operation_log]

        @classmethod
        def export_plugin_operation_log_list_services(
            cls,
            operation_log_list: list[PluginOperationLogDetailModel],
            operation_dict: dict[str, str],
        ) -> bytes:
            """记录审计导出字典映射。"""
            recorded.update(
                {
                    'operation_count': len(operation_log_list),
                    'operation_dict': operation_dict,
                }
            )
            return b'plugin audit export'

    class FakePluginOperationService:
        """
        测试用插件操作服务。
        """

        @classmethod
        async def get_plugin_operation_dict_services(cls, query_db: object) -> dict[str, str]:
            """返回测试用操作类型字典。"""
            recorded['dict_query_db'] = query_db
            return {'config_set': '配置保存'}

    monkeypatch.setattr(plugin_controller, 'PluginService', FakePluginService)
    monkeypatch.setattr(plugin_controller, 'PluginOperationService', FakePluginOperationService)
    query_db = FakeAsyncSession()

    response = await plugin_controller.export_system_plugin_operation_log_list(
        request=build_request('/system/plugin/operation-log/export'),
        operation_log_export_query=PluginOperationLogExportQueryModel(exportLimit=10),
        query_db=query_db,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert response.status_code == HTTP_OK
    assert b''.join(chunks) == b'plugin audit export'
    assert recorded == {
        'query_db': query_db,
        'export_limit': 10,
        'dict_query_db': query_db,
        'operation_count': 1,
        'operation_dict': {'config_set': '配置保存'},
    }
