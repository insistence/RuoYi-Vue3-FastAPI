from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import pytest

from system.test_plugin_management import (
    PLUGIN_ID,
    PLUGIN_WARNING,
    plugin_payload,
    validate_blocked_preview,
    validate_capability,
    validate_dependency_report,
    validate_install_plan,
    validate_operation_envelope,
)

pytestmark = pytest.mark.harness


def capability(frontend: str = 'built', backend: str = 'service') -> dict:
    """构造与 CI 中源码 AI 插件一致的能力报告。"""
    warnings = []
    if backend == 'service':
        warnings.append('当前为服务运行模式，请在维护窗口执行插件变更。')
    if frontend == 'built':
        warnings.append('当前为已构建前端环境，需要重新构建前端。')
    blocked = bool(warnings)
    return {
        'pluginId': PLUGIN_ID,
        'frontendMode': frontend,
        'backendRuntimeMode': backend,
        'hasFrontendResources': True,
        'frontendBuildRequired': True,
        'frontendRuntimeManageable': frontend != 'built',
        'backendRuntimeManageable': backend != 'service',
        'runtimeManageable': not blocked,
        'blockedOperations': ['batch_install', 'dependency_install'] if blocked else [],
        'warnings': warnings,
        'primaryReason': warnings[0] if blocked else '',
    }


def dependency_report(*, installed: bool, satisfied: bool, skipped: bool = False) -> dict:
    """缺失、版本不满足与 built 模式跳过检查有不同且可验证的语义。"""
    ok = skipped or (installed and satisfied)
    return {
        'pluginId': PLUGIN_ID,
        'ok': ok,
        'dependencyOk': ok,
        'message': '插件依赖已满足' if ok else '插件依赖存在问题',
        'dependencies': [
            {
                'requirement': 'example==1.0',
                'name': 'example',
                'installed': installed,
                'versionSatisfied': satisfied,
                'status': 'skipped' if skipped else 'checked',
                'ok': ok,
                'message': '依赖已跳过' if skipped else '已满足' if ok else '依赖缺失或版本不满足',
            }
        ],
        'missingDependencies': [] if skipped or installed else ['example'],
        'unsatisfiedDependencies': ['example'] if not skipped and installed and not satisfied else [],
    }


def install_plan(runtime: dict) -> dict:
    """有效拓扑与生产环境阻断分别保留，模拟已观测到的 CI 响应结构。"""
    blocked = not runtime['runtimeManageable']
    return {
        'ok': not blocked,
        'message': '插件批量操作计划存在环境阻断项' if blocked else '插件批量操作计划生成完成',
        'operation': 'install',
        'databaseAvailable': True,
        'databaseError': None,
        'plan': {
            'ok': True,
            'operation': 'install',
            'requestedPluginIds': [PLUGIN_ID],
            'orderedPluginIds': [PLUGIN_ID],
            'blockers': [],
            'blockerCount': 0,
            'items': [{'pluginId': PLUGIN_ID, 'ready': True}],
        },
        'capabilityBlockers': [
            {
                'pluginId': PLUGIN_ID,
                'operation': 'batch_install',
                'message': runtime['primaryReason'],
                'capability': deepcopy(runtime),
            }
        ]
        if blocked
        else [],
    }


def envelope(data: dict) -> dict:
    """响应封装的成功字段必须与业务结果对应。"""
    return {
        'code': HTTPStatus.OK if data['ok'] else PLUGIN_WARNING,
        'success': data['ok'],
        'msg': data['message'],
        'data': data,
    }


@pytest.mark.parametrize(
    ('installed', 'satisfied', 'skipped'),
    [(True, True, False), (False, False, False), (True, False, False), (False, False, True)],
)
def test_dependency_contract_accepts_only_explained_results(installed: bool, satisfied: bool, skipped: bool) -> None:
    report = dependency_report(installed=installed, satisfied=satisfied, skipped=skipped)
    validate_dependency_report(validate_operation_envelope(envelope(report)))


@pytest.mark.parametrize('field', ['missingDependencies', 'unsatisfiedDependencies', 'dependencyOk', 'message'])
def test_dependency_contract_rejects_unexplained_failure(field: str) -> None:
    report = dependency_report(installed=False, satisfied=False)
    report[field] = {
        'missingDependencies': [],
        'unsatisfiedDependencies': ['different'],
        'dependencyOk': True,
        'message': '接口异常',
    }[field]
    with pytest.raises(AssertionError):
        validate_dependency_report(report)


@pytest.mark.parametrize(
    ('frontend', 'backend'),
    [('dev', 'dev'), ('dev', 'maintenance'), ('built', 'dev'), ('dev', 'service'), ('built', 'service')],
)
def test_plan_contract_distinguishes_runtime_capability(frontend: str, backend: str) -> None:
    runtime = capability(frontend, backend)
    payload = validate_operation_envelope(envelope(install_plan(runtime)))
    assert validate_install_plan(payload, runtime) is (not runtime['runtimeManageable'])


@pytest.mark.parametrize(
    'corruption',
    ['no_blocker', 'wrong_operation', 'wrong_plugin', 'wrong_mode', 'database_error', 'unexpected_success'],
)
def test_plan_contract_rejects_unrelated_or_inconsistent_failure(corruption: str) -> None:
    runtime = capability()
    payload = install_plan(runtime)
    if corruption == 'no_blocker':
        payload['capabilityBlockers'] = []
    elif corruption == 'wrong_operation':
        payload['capabilityBlockers'][0]['operation'] = 'uninstall'
    elif corruption == 'wrong_plugin':
        payload['capabilityBlockers'][0]['pluginId'] = 'other'
    elif corruption == 'wrong_mode':
        payload['capabilityBlockers'][0]['capability'] = capability('dev', 'dev')
    elif corruption == 'database_error':
        payload['databaseAvailable'] = False
        payload['databaseError'] = 'connection failed'
    else:
        payload['ok'] = True
    with pytest.raises(AssertionError):
        validate_install_plan(payload, runtime)


@pytest.mark.parametrize('corruption', ['server_error', 'success_flag', 'missing_payload', 'wrong_message'])
def test_operation_envelope_does_not_hide_errors(corruption: str) -> None:
    payload = envelope(install_plan(capability()))
    if corruption == 'server_error':
        payload['code'] = HTTPStatus.INTERNAL_SERVER_ERROR
    elif corruption == 'success_flag':
        payload['success'] = True
    elif corruption == 'missing_payload':
        del payload['data']
    else:
        payload['msg'] = '接口异常'
    with pytest.raises((AssertionError, KeyError)):
        validate_operation_envelope(payload)


async def test_operation_payload_rejects_http_failure_even_with_valid_business_data() -> None:
    response = MagicMock(
        status=HTTPStatus.INTERNAL_SERVER_ERROR, json=AsyncMock(return_value=envelope(install_plan(capability())))
    )
    with pytest.raises(AssertionError):
        await plugin_payload(response)
    response.json.assert_not_awaited()


def test_capability_rejects_unexplained_blocked_operations_in_development() -> None:
    runtime = capability('dev', 'dev')
    runtime['blockedOperations'] = ['batch_install']
    with pytest.raises(AssertionError):
        validate_capability(runtime, 'batch_install')


@pytest.mark.parametrize('unsafe_field', [None, 'dryRun', 'results'])
def test_dependency_preview_requires_explicit_safe_environment_block(unsafe_field: str | None) -> None:
    runtime = capability()
    preview = {
        'ok': False,
        'status': 'blocked',
        'pluginId': PLUGIN_ID,
        'operation': 'dependency_install',
        'dryRun': True,
        'capability': runtime,
        'message': '当前环境不允许执行该插件操作',
        'suggestion': '请在开发模式或维护窗口执行插件变更。',
    }
    if unsafe_field:
        preview[unsafe_field] = False if unsafe_field == 'dryRun' else [{'command': 'pip install example'}]
        with pytest.raises(AssertionError):
            validate_blocked_preview(preview, runtime)
    else:
        validate_blocked_preview(validate_operation_envelope(envelope(preview)), runtime)
