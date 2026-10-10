import importlib.util
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str) -> ModuleType:
    """
    按文件路径加载 CI 脚本，避免依赖仓库外的模块搜索路径。

    :param name: 不含扩展名的脚本名称
    :return: 已执行模块顶层定义的脚本模块
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / '.github/scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compose = load_script('check_compose')
reports = load_script('check_test_report')


@pytest.fixture
def configuration() -> dict[str, Any]:
    """提供前端、nginx 和后端框架一致的 Compose 配置。"""
    frontend = ROOT / 'ruoyi-fastapi-frontend/vue2/web'
    return {
        'services': {
            'ruoyi-frontend': {
                'build': {'context': str(frontend), 'dockerfile': 'Dockerfile'},
                'volumes': [
                    {'source': str(frontend / 'bin/nginx.dockermy.conf'), 'target': '/etc/nginx/conf.d/default.conf'}
                ],
            },
            'ruoyi-backend-my': {'environment': {'RUOYI_PLUGIN_FRONTEND_FRAMEWORK': 'vue2'}},
        }
    }


def test_compose_accepts_consistent_framework(configuration: dict[str, Any]) -> None:
    """框架一致的 Compose 配置可以通过校验。"""
    compose.validate_configuration(configuration, 'vue2', 'my', ROOT)


@pytest.mark.parametrize('component', ['build', 'nginx', 'backend'])
def test_compose_rejects_mixed_framework_deployment(configuration: dict[str, Any], component: str) -> None:
    """前端、nginx 或后端混用框架时拒绝部署配置。"""
    invalid = deepcopy(configuration)
    if component == 'build':
        invalid['services']['ruoyi-frontend']['build']['context'] = str(ROOT / 'ruoyi-fastapi-frontend/vue3/web')
    elif component == 'nginx':
        invalid['services']['ruoyi-frontend']['volumes'][0]['source'] = str(
            ROOT / 'ruoyi-fastapi-frontend/vue3/web/bin/nginx.dockermy.conf'
        )
    else:
        invalid['services']['ruoyi-backend-my']['environment']['RUOYI_PLUGIN_FRONTEND_FRAMEWORK'] = 'vue3'
    with pytest.raises(ValueError):
        compose.validate_configuration(invalid, 'vue2', 'my', ROOT)


@pytest.mark.parametrize(
    'cases',
    ['', '<testcase><skipped /></testcase>', '<testcase><failure /></testcase>', '<testcase><error /></testcase>'],
)
def test_report_rejects_empty_skipped_or_failed_verification(tmp_path: Path, cases: str) -> None:
    """空报告、全部跳过和失败用例都不能视为验收成功。"""
    report = tmp_path / 'results.xml'
    report.write_text(f'<testsuites><testsuite>{cases}</testsuite></testsuites>', encoding='utf-8')
    with pytest.raises(ValueError):
        reports.check_report(report)


def test_expected_platform_skip_still_requires_executed_tests(tmp_path: Path) -> None:
    """允许预期平台跳过时仍要求实际执行测试。"""
    report = tmp_path / 'results.xml'
    report.write_text(
        '<testsuites><testsuite><testcase/><testcase><skipped/></testcase></testsuite></testsuites>', encoding='utf-8'
    )
    assert reports.check_report(report, allow_skips=True) == (1, 1)


def test_missing_report_is_not_success(tmp_path: Path) -> None:
    """报告缺失时不能视为验收成功。"""
    with pytest.raises(FileNotFoundError):
        reports.check_report(tmp_path / 'missing.xml')
