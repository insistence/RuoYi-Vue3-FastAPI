from cli.utils import SHELL_TEXT_FORMATTER


class ConfigCommandPresenter:
    """
    参数配置命令文本渲染器。

    该渲染器负责将 `config` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_config_list_text(self, payload: dict[str, object]) -> str:
        """
        将参数配置列表结果渲染为文本摘要。

        :param payload: 参数配置列表结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
        ]

        filters = payload.get('filters')
        if isinstance(filters, dict):
            lines.extend(self._build_config_filter_lines(filters))

        page_payload = payload.get('page')
        if isinstance(page_payload, dict):
            rows = page_payload.get('rows')
            lines.append(
                'page: '
                f'{page_payload.get("pageNum", "-")}/{page_payload.get("pages", "-")} '
                f'(page_size={page_payload.get("pageSize", "-")}, total={page_payload.get("total", "-")})'
            )
            lines.append(f'count: {len(rows) if isinstance(rows, list) else 0}')
            if not isinstance(rows, list) or not rows:
                lines.append('configs: none')
                return '\n'.join(lines)
            lines.append('configs:')
            for row in rows:
                if isinstance(row, dict):
                    lines.extend([f'  {item}' for item in self._build_config_item_lines(row)])
            return '\n'.join(lines)

        items = payload.get('items')
        lines.append(f'count: {payload.get("count", 0)}')
        if not isinstance(items, list) or not items:
            lines.append('configs: none')
            return '\n'.join(lines)

        lines.append('configs:')
        for item in items:
            if isinstance(item, dict):
                lines.extend([f'  {line}' for line in self._build_config_item_lines(item)])
        return '\n'.join(lines)

    def build_config_get_text(self, payload: dict[str, object]) -> str:
        """
        将单个参数配置详情结果渲染为文本摘要。

        :param payload: 参数配置详情结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'key: {payload.get("key", "")}',
            f'source: {payload.get("source", "")}',
        ]

        if payload.get('source') == 'both':
            lines.append(f'in_sync: {str(payload.get("inSync", False)).lower()}')

        if payload.get('source') in {'db', 'both'}:
            lines.extend(self._build_config_detail_section('database', payload.get('database')))
        if payload.get('source') in {'cache', 'both'}:
            lines.extend(self._build_config_detail_section('cache', payload.get('cache')))
        return '\n'.join(lines)

    def build_config_doctor_text(self, payload: dict[str, object]) -> str:
        """
        将参数配置诊断结果渲染为文本摘要。

        :param payload: 参数配置诊断结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'message: {payload.get("message", "-")}',
            f'database_count: {payload.get("databaseCount", 0)}',
            f'cache_count: {payload.get("cacheCount", 0)}',
            f'missing_in_cache_count: {payload.get("missingInCacheCount", 0)}',
            f'orphan_in_cache_count: {payload.get("orphanInCacheCount", 0)}',
            f'mismatch_count: {payload.get("mismatchCount", 0)}',
            f'sample_limit: {payload.get("sampleLimit", 0)}',
        ]
        lines.extend(self._build_config_doctor_items('missing_in_cache', payload.get('missingInCache')))
        lines.extend(self._build_config_doctor_items('orphan_in_cache', payload.get('orphanInCache')))
        lines.extend(self._build_config_doctor_items('mismatch_keys', payload.get('mismatchKeys')))
        return '\n'.join(lines)

    @staticmethod
    def _build_config_filter_lines(filters: dict[str, object]) -> list[str]:
        """
        构建参数配置过滤条件文本行。

        :param filters: 过滤条件字典
        :return: 过滤条件文本行列表
        """
        active_filters = []
        for key, value in filters.items():
            if value in (None, '', False):
                continue
            active_filters.append(f'{SHELL_TEXT_FORMATTER.to_snake_case(key)}={value}')
        if not active_filters:
            return ['filters: none']
        return ['filters:', *[f'  - {item}' for item in active_filters]]

    @staticmethod
    def _build_config_item_lines(config_item: dict[str, object]) -> list[str]:
        """
        构建单条参数配置记录的文本行。

        :param config_item: 单条参数配置记录
        :return: 文本行列表
        """
        config_id = config_item.get('configId', '-')
        config_key = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configKey', ''), 50)
        config_name = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configName', ''), 24)
        config_type = config_item.get('configType', '-')
        config_value = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configValue', ''), 80)
        remark = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('remark', ''), 60)
        return [
            f'- [{config_id}] {config_key} | 名称: {config_name} | 内置: {config_type}',
            f'  value: {config_value or "-"}',
            f'  remark: {remark or "-"}',
        ]

    @staticmethod
    def _build_config_detail_section(title: str, config_item: dict[str, object] | None) -> list[str]:
        """
        构建单个配置来源的详情文本段落。

        :param title: 段落标题
        :param config_item: 配置详情字典
        :return: 文本行列表
        """
        if not isinstance(config_item, dict):
            return [f'{title}: none']

        config_key = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configKey', ''), 60)
        config_name = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configName', ''), 30)
        config_value = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('configValue', ''), 120)
        config_type = config_item.get('configType', '-')
        remark = SHELL_TEXT_FORMATTER.truncate_text(config_item.get('remark', ''), 80)
        config_id = config_item.get('configId', '-')
        return [
            f'{title}:',
            f'  id: {config_id}',
            f'  key: {config_key or "-"}',
            f'  name: {config_name or "-"}',
            f'  value: {config_value or "-"}',
            f'  type: {config_type}',
            f'  remark: {remark or "-"}',
        ]

    @staticmethod
    def _build_config_doctor_items(title: str, items: list[object] | object) -> list[str]:
        """
        构建配置诊断问题示例段落。

        :param title: 段落标题
        :param items: 问题键名列表
        :return: 文本行列表
        """
        if not isinstance(items, list) or not items:
            return [f'{title}: none']
        return [f'{title}:', *[f'  - {item}' for item in items]]
