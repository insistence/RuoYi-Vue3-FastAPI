# ruff: noqa: F403, F405

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import discover_plugins
from tests.plugin_runtime_helpers import *


def test_plugin_catalog_list_payload_model_serializes_payload(tmp_path: Path) -> None:
    """
    校验插件目录列表结构化模型可序列化为现有负载契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    registered_plugin = PluginRegistry.build(discover_plugins(backend_root / 'plugins')).list_plugins()[0]

    payload = PluginPayloadBuilder.build_plugin_list_payload([registered_plugin])

    assert payload['ok'] is True
    assert payload['count'] == 1
    assert payload['plugins'][0]['pluginId'] == 'demo'
    assert payload['plugins'][0]['enabled'] is False


def test_plugin_catalog_info_payload_model_serializes_payload(tmp_path: Path) -> None:
    """
    校验插件目录详情结构化模型可序列化为现有负载契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
dependencies:
  python:
    - openai>=2.17.0
permissions:
  - code: demo:list
    name: 演示列表
    description: 查看演示页面
""",
    )
    discovered_plugin = discover_plugins(backend_root / 'plugins')[0]
    dependency = DependencyCheckItem(
        kind='python',
        requirement='openai>=2.17.0',
        name='openai',
        installed=True,
        version_satisfied=True,
        installed_version='2.17.0',
        required_version='>=2.17.0',
        message='依赖已满足',
    )

    payload = PluginPayloadBuilder.build_plugin_info_payload(discovered_plugin, [dependency])

    assert payload['ok'] is True
    assert payload['plugin']['pluginId'] == 'demo'
    assert payload['plugin']['backend']['module'] == 'plugins.demo'
    assert payload['plugin']['permissions'][0] == {
        'code': 'demo:list',
        'name': '演示列表',
        'description': '查看演示页面',
    }
    assert payload['plugin']['dependencies'][0]['name'] == 'openai'


def test_plugin_catalog_summary_payload_model_serializes_payload(tmp_path: Path) -> None:
    """
    校验插件目录摘要结构化模型可序列化为现有负载契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
permissions:
  - demo:list
""",
    )
    discovered_plugin = discover_plugins(backend_root / 'plugins')[0]

    payload = PluginPayloadBuilder.build_plugin_summary(discovered_plugin, enabled=False, status='installed')

    assert payload['pluginId'] == 'demo'
    assert payload['name'] == '演示插件'
    assert payload['enabled'] is False
    assert payload['status'] == 'installed'
    assert payload['permissionCount'] == 1


def test_plugin_catalog_database_state_payload_model_serializes_payload() -> None:
    """
    校验插件目录数据库状态结构化模型可序列化为现有负载契约。

    :return: None
    """
    database_plugin = SimpleNamespace(
        installed_version='1.0.0',
        enabled='1',
        status='installed',
        last_error='',
    )

    success_payload = PluginPayloadBuilder.build_database_state(database_plugin)
    failure_payload = PluginPayloadBuilder.build_database_state(None, database_error='数据库不可用')

    assert success_payload['available'] is True
    assert success_payload['installed'] is True
    assert success_payload['installedVersion'] == '1.0.0'
    assert success_payload['enabled'] == '1'
    assert failure_payload == {
        'available': False,
        'installed': False,
        'error': '数据库不可用',
    }
