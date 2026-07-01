import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.scanner import PluginScanner  # noqa: E402
from plugins.core.runtime.health import PluginHealthChecker  # noqa: E402


def write_plugin_with_health(plugin_root: Path, health_content: str, checker_path: str = 'health:check') -> None:
    """
    写入带健康检查的测试插件。

    :param plugin_root: 插件根目录
    :param health_content: 健康检查文件内容
    :param checker_path: 健康检查声明路径
    :return: None
    """
    plugin_root.mkdir(parents=True)
    (plugin_root / 'health.py').write_text(health_content, encoding='utf-8')
    (plugin_root / 'plugin.yaml').write_text(
        f"""
id: demo_health
name: Demo Health
version: 1.0.0
backend:
  module: plugins.demo_health
  health:
    checker: {checker_path}
""",
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_plugin_health_checker_executes_async_checker_with_context(tmp_path: Path) -> None:
    """
    校验健康检查器可以执行异步 checker 并传入上下文。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    """
    校验健康检查器支持布尔返回值。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, 'def check():\n    return False\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is False
    assert result.status == 'unhealthy'
    assert result.error is None


@pytest.mark.asyncio
async def test_plugin_health_checker_returns_unknown_when_checker_missing(tmp_path: Path) -> None:
    """
    校验未声明健康检查时返回 unknown。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    plugin_root.mkdir(parents=True)
    (plugin_root / 'plugin.yaml').write_text(
        """
id: demo_health
name: Demo Health
version: 1.0.0
backend:
  module: plugins.demo_health
""",
        encoding='utf-8',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is True
    assert result.status == 'unknown'
    assert result.checker is None


@pytest.mark.asyncio
async def test_plugin_health_checker_rejects_foreign_plugin_module(tmp_path: Path) -> None:
    """
    校验健康检查不能指向其他插件模块。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(plugin_root, 'def check():\n    return True\n', checker_path='plugins.other.health:check')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin).check()

    assert result.ok is False
    assert result.status == 'error'
    assert '当前插件模块' in str(result.error)


@pytest.mark.asyncio
async def test_plugin_health_checker_reports_timeout(tmp_path: Path) -> None:
    """
    校验健康检查超时时返回 timeout 状态而不是抛出异常。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
async def test_plugin_health_checker_reports_sync_timeout(tmp_path: Path) -> None:
    """
    校验同步健康检查阻塞时也会返回 timeout。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_health'
    write_plugin_with_health(
        plugin_root,
        'import time\ndef check(context):\n    time.sleep(1)\n    return True\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHealthChecker(discovered_plugin, timeout_seconds=0.01).check()

    assert result.ok is False
    assert result.status == 'timeout'
    assert result.message == '插件健康检查执行超时'
