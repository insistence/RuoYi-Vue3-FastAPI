import sys
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.discovery.scanner import PluginScanner
from plugins.core.manifest.schema import EXPLICIT_MANIFEST_VERSION
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.health import PluginHealthChecker


@pytest.fixture(autouse=True)
def isolate_health_plugin_modules() -> Generator[None, None, None]:
    """隔离测试插件模块，避免 v2 加载器复用其他临时目录的旧模块。"""
    for name in list(sys.modules):
        if name == 'plugins.demo_health' or name.startswith('plugins.demo_health.'):
            sys.modules.pop(name, None)
    yield
    for name in list(sys.modules):
        if name == 'plugins.demo_health' or name.startswith('plugins.demo_health.'):
            sys.modules.pop(name, None)
    package = sys.modules.get('plugins')
    if package is not None and hasattr(package, 'demo_health'):
        delattr(package, 'demo_health')


def write_plugin_with_health(
    plugin_root: Path,
    health_content: str,
    checker_path: str | None = 'health:check',
    *,
    manifest_version: int = 1,
) -> None:
    """写入带健康检查的测试插件。"""
    plugin_root.mkdir(parents=True)
    (plugin_root / '__init__.py').write_text('', encoding='utf-8')
    (plugin_root / 'health.py').write_text(health_content, encoding='utf-8')
    entrypoint = ''
    if manifest_version == EXPLICIT_MANIFEST_VERSION:
        entrypoint = '  entrypoint: plugins.demo_health:create_plugin\n'
        if checker_path == 'health:check':
            checker_path = 'plugins.demo_health.health:check'
    (plugin_root / 'plugin.yaml').write_text(
        f"""
manifestVersion: {manifest_version}
id: demo_health
name: Demo Health
version: 1.0.0
backend:
  module: plugins.demo_health
{entrypoint}  health:
    checker: {checker_path or 'null'}
""",
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_plugin_health_checker_executes_async_checker_with_context(tmp_path: Path) -> None:
    """校验健康检查器可以执行异步 checker 并传入上下文。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(
        plugin_root,
        'async def check(context):\n'
        "    return {'ok': True, 'status': 'healthy', 'message': context.plugin_id, 'details': {'ready': True}}\n",
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is True
    assert result.status == 'healthy'
    assert result.message == 'demo_health'
    assert result.details == {'ready': True}
    assert result.checker == 'health:check'


@pytest.mark.asyncio
async def test_plugin_health_checker_normalizes_boolean_result(tmp_path: Path) -> None:
    """校验健康检查器支持布尔返回值。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, 'async def check():\n    return False\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is False
    assert result.status == 'unhealthy'
    assert result.error is None


@pytest.mark.asyncio
@pytest.mark.parametrize('manifest_version', [1, 2])
async def test_plugin_health_checker_returns_unknown_when_checker_missing(
    tmp_path: Path, manifest_version: int
) -> None:
    """校验未声明健康检查时返回 unknown。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, '', checker_path=None, manifest_version=manifest_version)
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is True
    assert result.status == 'unknown'
    assert result.checker is None


@pytest.mark.asyncio
async def test_plugin_health_checker_rejects_foreign_plugin_module(tmp_path: Path) -> None:
    """校验健康检查不能指向其他插件模块。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, 'def check():\n    return True\n', checker_path='plugins.other.health:check')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is False
    assert result.status == 'error'
    assert '当前插件模块' in str(result.error)


@pytest.mark.asyncio
async def test_plugin_health_checker_reports_timeout(tmp_path: Path) -> None:
    """校验健康检查超时时返回 timeout 状态而不是抛出异常。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(
        plugin_root,
        'import asyncio\nasync def check(context):\n    await asyncio.sleep(1)\n    return True\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin, timeout_seconds=0.01).check()

    assert result.ok is False
    assert result.status == 'timeout'
    assert result.message == '插件健康检查执行超时'
    assert '超过 0.01 秒' in str(result.error)


@pytest.mark.asyncio
async def test_plugin_health_checker_rejects_sync_checker_without_executing_it(tmp_path: Path) -> None:
    """校验同步健康检查会在执行前被拒绝，避免超时后继续运行。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(
        plugin_root,
        'def check(context):\n    context.app.append("executed")\n    return True\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    app: list[str] = []

    result = await PluginHealthChecker(discovered_plugin, timeout_seconds=0.01).check(app=app)

    assert result.ok is False
    assert result.status == 'error'
    assert '必须使用 async def' in str(result.error)
    assert app == []


@pytest.mark.asyncio
@pytest.mark.parametrize('raw_result', [True, False, {'ok': True}, {'ok': False}])
async def test_v2_health_checker_accepts_explicit_boolean_results(tmp_path: Path, raw_result: object) -> None:
    """v2 支持布尔结果和显式 ok 字段，保留健康与不健康的区别。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, f'async def check(context):\n    return {raw_result!r}\n', manifest_version=2)
    plugin = PluginScanner(plugin_root.parent).load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(plugin).check()

    expected = raw_result['ok'] if isinstance(raw_result, dict) else raw_result
    assert result.ok is expected
    assert result.status == ('healthy' if expected else 'unhealthy')
    assert result.error is None


@pytest.mark.asyncio
async def test_v2_health_checker_preserves_structured_result_details(tmp_path: Path) -> None:
    """严格校验 ok 后仍保留插件的状态、说明和结构化检查详情。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(
        plugin_root,
        'async def check(context):\n'
        "    return {'ok': False, 'status': 'degraded', 'message': '依赖不可用', 'details': {'database': False}}\n",
        manifest_version=2,
    )
    plugin = PluginScanner(plugin_root.parent).load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(plugin).check()

    assert result.ok is False
    assert result.status == 'degraded'
    assert result.message == '依赖不可用'
    assert result.details == {'database': False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'raw_result',
    [None, 'unhealthy', 0, 1, [], {}, {'healthy': True}, {'ok': 'false'}, {'ok': 0}, {'ok': 1}, {'ok': None}],
)
async def test_v2_health_checker_rejects_invalid_results(tmp_path: Path, raw_result: object) -> None:
    """v2 的缺字段、字符串及真假整数等结果不能误判为健康。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, f'async def check(context):\n    return {raw_result!r}\n', manifest_version=2)
    plugin = PluginScanner(plugin_root.parent).load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(plugin).check()

    assert result.ok is False
    assert result.status == 'error'
    assert 'v2 插件健康检查必须返回' in str(result.error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('raw_result', 'expected'),
    [(None, True), ('unhealthy', True), ({}, True), ({'ok': 'false'}, True), ({'healthy': False}, False)],
)
async def test_v1_health_checker_preserves_legacy_result_coercion(
    tmp_path: Path, raw_result: object, expected: bool
) -> None:
    """v1 继续保留无返回值、旧 healthy 字段及布尔转换的兼容行为。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, f'async def check(context):\n    return {raw_result!r}\n')
    plugin = PluginScanner(plugin_root.parent).load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(plugin).check()

    assert result.ok is expected
    assert result.status == ('healthy' if expected else 'unhealthy')
    assert result.error is None


@pytest.mark.asyncio
@pytest.mark.parametrize('raw_result', [None, {'ok': 'false'}])
async def test_v2_invalid_health_result_prevents_router_activation(tmp_path: Path, raw_result: object) -> None:
    """无效健康结果必须阻止实际路由激活，不能只在检查接口报告错误。"""
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, f'async def check(context):\n    return {raw_result!r}\n', manifest_version=2)
    (plugin_root / '__init__.py').write_text(
        'from fastapi import APIRouter\n'
        'from plugins.core.sdk import PluginDefinition\n'
        'def create_plugin(host):\n'
        "    router = APIRouter(prefix='/demo_health')\n"
        "    @router.get('/info')\n"
        '    async def info():\n'
        "        return {'ready': True}\n"
        '    return PluginDefinition(routers=(router,))\n',
        encoding='utf-8',
    )
    discovered = PluginScanner(plugin_root.parent).load_manifest(plugin_root / 'plugin.yaml')
    plugin = RegisteredPlugin(discovered, None, True, 'installed')
    app = FastAPI()
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    runtime.prepare(plugin, app, startup_write_enabled=False)
    try:
        with pytest.raises(RuntimeError, match='健康检查'):
            await runtime.activate('demo_health', app)
        assert not runtime.loaded['demo_health'].active
        assert all(getattr(route, 'path', '') != '/demo_health/info' for route in app.routes)
    finally:
        await runtime.shutdown()
