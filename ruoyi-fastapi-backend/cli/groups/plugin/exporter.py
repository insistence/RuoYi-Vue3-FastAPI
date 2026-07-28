import json
from pathlib import Path
from typing import Any

from cli.exit_codes import ARGUMENT_ERROR


class PluginCommandFileAdapter:
    """
    插件命令文件导入导出适配器。

    这些能力只服务 CLI 参数交互，不属于插件 core runtime。
    """

    @classmethod
    def write_markdown_file(
        cls,
        payload: dict[str, Any],
        output_file: str,
        *,
        content_key: str,
        failure_message: str,
    ) -> dict[str, Any]:
        """
        写入 Markdown 文本文件。

        :param payload: 原始命令负载
        :param output_file: 输出文件路径
        :param content_key: Markdown 内容字段名
        :param failure_message: 写入失败提示前缀
        :return: 附加导出结果后的命令负载
        """
        return cls._write_text_file(
            payload,
            output_file,
            content=str(payload.get(content_key, '')),
            failure_message=failure_message,
        )

    @classmethod
    def write_json_file(
        cls,
        payload: dict[str, Any],
        output_file: str,
        *,
        failure_message: str,
    ) -> dict[str, Any]:
        """
        写入 JSON 文件。

        :param payload: 原始命令负载
        :param output_file: 输出文件路径
        :param failure_message: 写入失败提示前缀
        :return: 附加导出结果后的命令负载
        """
        content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return cls._write_text_file(payload, output_file, content=content, failure_message=failure_message)

    @staticmethod
    def read_config_import_file(input_file: str) -> dict[str, Any]:
        """
        读取插件配置导入 JSON 文件。

        :param input_file: 配置导入 JSON 文件路径
        :return: 配置导入负载
        """
        if not input_file.strip():
            return {'ok': False, 'message': '导入配置必须指定 --input-file', 'values': {}}

        input_path = Path(input_file).expanduser().resolve()
        try:
            raw_payload = json.loads(input_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            return {'ok': False, 'message': f'读取配置导入文件失败：{exc}', 'values': {}}

        if not isinstance(raw_payload, dict):
            return {'ok': False, 'message': '配置导入文件必须是 JSON 对象', 'values': {}}
        values = raw_payload.get('values', raw_payload)
        if not isinstance(values, dict):
            return {'ok': False, 'message': '配置导入文件 values 必须是 JSON 对象', 'values': {}}

        return {'ok': True, 'message': '配置导入文件读取完成', 'values': values}

    @staticmethod
    def _write_text_file(
        payload: dict[str, Any],
        output_file: str,
        *,
        content: str,
        failure_message: str,
    ) -> dict[str, Any]:
        """
        写入文本文件并补充导出状态。

        :param payload: 原始命令负载
        :param output_file: 输出文件路径
        :param content: 文件内容
        :param failure_message: 写入失败提示前缀
        :return: 附加导出结果后的命令负载
        """
        export_payload = dict(payload)
        output_path = Path(output_file).expanduser().resolve()
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding='utf-8')
            export_payload['outputFile'] = str(output_path)
            export_payload['exported'] = True
        except OSError as exc:
            export_payload['ok'] = False
            export_payload['message'] = f'{failure_message}：{exc}'
            export_payload['outputFile'] = str(output_path)
            export_payload['exported'] = False
            export_payload['exit_code'] = ARGUMENT_ERROR
        return export_payload
