import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ci_plan.py'
SPEC = importlib.util.spec_from_file_location('ci_plan', SCRIPT)
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)
FRONTEND_PROJECT_COUNT = 4
STANDARD_E2E_COMBINATION_COUNT = 4
FULL_E2E_COMBINATION_COUNT = 16


def test_readme_change_only_runs_quality() -> None:
    """仅文档变更时只执行质量检查。"""
    assert ci.build_plan(['README.md'])['required'] == {
        'quality': True,
        'backend': False,
        'frontend': False,
        'integration': False,
        'e2e': False,
        'native': False,
    }


@pytest.mark.parametrize(
    'path',
    [
        'ruoyi-fastapi-backend/cli/groups/plugin/options.py',
        'ruoyi-fastapi-backend/cli/groups/plugin/controller.py',
        'ruoyi-fastapi-backend/cli/runtime/plugin/service.py',
        'ruoyi-fastapi-backend/tests/module_plugin/controller/test_plugin_release_controller.py',
        'ruoyi-fastapi-backend/tests/sql/test_plugin_release_schema.py',
    ],
)
def test_shared_plugin_changes_retain_windows_and_release_coverage(path: str) -> None:
    """共享插件变更保留原生模块及发布验收覆盖。"""
    plan = ci.build_plan([path])
    assert plan['required']['backend']
    assert plan['required']['native']
    assert plan['release']


def test_native_builder_change_runs_native_verification() -> None:
    """原生构建器变更必须触发原生验收。"""
    plan = ci.build_plan(['ruoyi-fastapi-backend/scripts/build_native_plugin.py'])
    assert plan['required']['native']


def test_bundle_example_change_runs_both_web_consumers() -> None:
    """示例开发代理由两版 Web 测试直接引用，变更时均应执行。"""
    plan = ci.build_plan(['ruoyi-fastapi-backend/plugins/examples/python/bundle_demo/web/dev/mockRequest.js'])
    assert plan['frontend_matrix'] == {
        'include': [
            {'framework': 'vue2', 'target': 'web'},
            {'framework': 'vue3', 'target': 'web'},
        ]
    }


@pytest.mark.parametrize(
    'path',
    [
        'ruoyi-fastapi-backend/module_admin/service/login_service.py',
        'ruoyi-fastapi-backend/tests/scheduler_helpers.py',
        'ruoyi-fastapi-backend/tests/plugins/core/runtime/test_browser_session.py',
    ],
)
def test_shared_auth_and_test_helpers_keep_both_network_suites(path: str) -> None:
    """共享鉴权和测试夹具变更触发两版网络验收。"""
    plan = ci.build_plan([path])
    assert plan['required']['backend']
    assert plan['required']['integration']
    assert plan['network_frameworks'] == ['vue2', 'vue3']


@pytest.mark.parametrize(
    'path', ['.github/workflows/ci.yml', '.github/scripts/ci_plan.py', 'ruoyi-fastapi-backend/requirements-test.txt']
)
def test_ci_and_dependency_changes_select_every_category(path: str) -> None:
    """CI 及共享依赖变更覆盖全部任务分类。"""
    plan = ci.build_plan([path])
    assert all(plan['required'].values())
    assert len(plan['frontend_matrix']['include']) == FRONTEND_PROJECT_COUNT
    assert len(plan['e2e_matrix']['include']) == STANDARD_E2E_COMBINATION_COUNT


def test_mobile_change_does_not_build_other_projects_or_web_e2e() -> None:
    """单个移动端变更只选中对应工程。"""
    plan = ci.build_plan(['ruoyi-fastapi-frontend/vue2/mobile/src/utils/request.js'])
    assert plan['frontend_matrix'] == {'include': [{'framework': 'vue2', 'target': 'mobile'}]}
    assert not plan['required']['e2e']


@pytest.mark.parametrize(
    'path',
    [
        'ruoyi-fastapi-test/frontend/mobile-harness.mjs',
        'ruoyi-fastapi-test/frontend/mobile-behavior.mjs',
    ],
)
def test_shared_mobile_harness_runs_both_mobile_projects(path: str) -> None:
    """共享移动端测试工具变更同时验证两版工程。"""
    plan = ci.build_plan([path])
    assert plan['required']['frontend']
    assert plan['frontend_matrix'] == {
        'include': [
            {'framework': 'vue2', 'target': 'mobile'},
            {'framework': 'vue3', 'target': 'mobile'},
        ]
    }
    assert not plan['required']['e2e']


def test_web_change_selects_matching_framework_and_both_databases() -> None:
    """Web 变更使用对应框架并覆盖两类数据库。"""
    plan = ci.build_plan(['ruoyi-fastapi-frontend/vue2/web/src/views/login.vue'])
    assert plan['network_frameworks'] == ['vue2']
    assert {(row['framework'], row['database'], row['python']) for row in plan['e2e_matrix']['include']} == {
        ('vue2', 'mysql', '3.12'),
        ('vue2', 'postgresql', '3.12'),
    }


def test_shared_time_contract_runs_all_frontends_and_database_checks() -> None:
    """共享时间契约触发全部前端及数据库检查。"""
    plan = ci.build_plan(['ruoyi-fastapi-test/time-contract/fixtures.json'])
    assert len(plan['frontend_matrix']['include']) == FRONTEND_PROJECT_COUNT
    assert plan['database']


def test_framework_move_keeps_both_sides_in_plan() -> None:
    """跨框架移动文件保留来源和目标两侧验证。"""
    plan = ci.build_plan(
        ['ruoyi-fastapi-frontend/vue2/web/src/utils/demo.js', 'ruoyi-fastapi-frontend/vue3/web/src/utils/demo.js']
    )
    assert plan['network_frameworks'] == ['vue2', 'vue3']


def test_full_run_preserves_python_database_and_framework_combinations() -> None:
    """完整运行保留 Python、数据库和框架的全部组合。"""
    plan = ci.build_plan([], full=True)
    assert all(plan['required'].values())
    assert len(plan['e2e_matrix']['include']) == FULL_E2E_COMBINATION_COUNT
    assert {row['python'] for row in plan['e2e_matrix']['include']} == {'3.10', '3.11', '3.12', '3.13'}


@pytest.mark.parametrize('result', ['failure', 'cancelled', 'skipped', None])
def test_gate_rejects_unsuccessful_required_job(result: str | None) -> None:
    """必跑任务失败、取消、跳过或缺失均不能通过门禁。"""
    plan = ci.build_plan(['README.md'])
    needs = {'plan': {'result': 'success'}, **{name: {'result': 'skipped'} for name in ci.CATEGORIES}}
    needs['quality']['result'] = result
    assert ci.check_results(plan, needs)


def test_gate_allows_only_unselected_jobs_to_skip() -> None:
    """只有未选中的任务允许跳过。"""
    plan = ci.build_plan(['README.md'])
    needs = {'plan': {'result': 'success'}, **{name: {'result': 'skipped'} for name in ci.CATEGORIES}}
    needs['quality']['result'] = 'success'
    assert ci.check_results(plan, needs) == []


def test_gate_fails_closed_when_plan_or_job_is_missing() -> None:
    """缺少执行计划或任务结果时门禁必须拒绝放行。"""
    assert ci.check_results({}, {})
    assert ci.check_results(ci.build_plan(['README.md']), {'plan': {'result': 'success'}})
