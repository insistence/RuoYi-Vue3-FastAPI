import json
from pathlib import Path

from cli.groups.plugin.exporter import PluginCommandFileAdapter


def test_plugin_command_file_adapter_writes_markdown_file(tmp_path: Path) -> None:
    """校验插件命令文件适配器写入 Markdown 文件。"""
    output_file = tmp_path / 'docs' / 'plugin.md'

    payload = PluginCommandFileAdapter.write_markdown_file(
        {'ok': True, 'markdown': '# Demo'},
        str(output_file),
        content_key='markdown',
        failure_message='插件文档导出失败',
    )

    assert payload['ok'] is True
    assert payload['exported'] is True
    assert payload['outputFile'] == str(output_file)
    assert output_file.read_text(encoding='utf-8') == '# Demo'


def test_plugin_command_file_adapter_writes_json_file(tmp_path: Path) -> None:
    """校验插件命令文件适配器写入 JSON 文件。"""
    output_file = tmp_path / 'diagnose.json'

    payload = PluginCommandFileAdapter.write_json_file(
        {'ok': True, 'pluginId': 'demo'},
        str(output_file),
        failure_message='插件诊断包导出失败',
    )

    assert payload['exported'] is True
    assert json.loads(output_file.read_text(encoding='utf-8')) == {'ok': True, 'pluginId': 'demo'}


def test_plugin_command_file_adapter_reads_config_import_values(tmp_path: Path) -> None:
    """校验插件命令文件适配器读取配置导入文件。"""
    input_file = tmp_path / 'config.json'
    input_file.write_text('{"values": {"enabled": true}}\n', encoding='utf-8')

    payload = PluginCommandFileAdapter.read_config_import_file(str(input_file))

    assert payload == {'ok': True, 'message': '配置导入文件读取完成', 'values': {'enabled': True}}


def test_plugin_command_file_adapter_reports_missing_config_import_file() -> None:
    """校验插件命令文件适配器报告缺少配置导入文件。"""
    payload = PluginCommandFileAdapter.read_config_import_file('')

    assert payload == {'ok': False, 'message': '导入配置必须指定 --input-file', 'values': {}}
