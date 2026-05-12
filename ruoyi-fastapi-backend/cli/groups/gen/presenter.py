from cli.utils import SHELL_TEXT_FORMATTER


class GenCommandPresenter:
    """
    代码生成命令文本渲染器。

    该渲染器负责将 `gen` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_gen_preview_text(self, payload: dict[str, object]) -> str:
        """
        将代码预览结果渲染为文本摘要。

        :param payload: 代码预览结果字典
        :return: 文本摘要
        """
        preview_payload = payload.get('preview')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'table_id: {payload.get("tableId", "-")}',
            f'template_count: {payload.get("templateCount", 0)}',
        ]
        if not isinstance(preview_payload, dict) or not preview_payload:
            lines.append('templates: none')
            return '\n'.join(lines)

        lines.append('templates:')
        for template_name, template_content in preview_payload.items():
            lines.extend([f'  {line}' for line in self._build_text_block(str(template_name), template_content)])
        return '\n'.join(lines)

    def build_gen_export_text(self, payload: dict[str, object]) -> str:
        """
        将代码导出结果渲染为文本摘要。

        :param payload: 代码导出结果字典
        :return: 文本摘要
        """
        table_names = payload.get('tableNames')
        results = payload.get('results')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'mode: {payload.get("mode", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'message: {payload.get("message", "-")}',
        ]
        if isinstance(table_names, list) and table_names:
            lines.append('table_names:')
            lines.extend(f'  - {table_name}' for table_name in table_names)
        else:
            lines.append('table_names: none')

        if payload.get('outputFile'):
            lines.append(f'output_file: {payload.get("outputFile")}')
        if payload.get('genPath'):
            lines.append(f'gen_path: {payload.get("genPath")}')
        if payload.get('size') is not None:
            lines.append(f'size: {payload.get("size")}')

        if isinstance(results, list) and results:
            lines.append('results:')
            lines.extend(
                f'  - {item.get("tableName", "-")}: {str(item.get("ok", False)).lower()} | {item.get("message", "-")}'
                for item in results
                if isinstance(item, dict)
            )
        return '\n'.join(lines)

    def build_gen_table_list_text(self, payload: dict[str, object], *, db_mode: bool = False) -> str:
        """
        将代码生成表列表或数据库表列表渲染为文本摘要。

        :param payload: 列表结果字典
        :param db_mode: 是否为数据库物理表列表模式
        :return: 文本摘要
        """
        lines = [f'ok: {str(payload.get("ok", False)).lower()}']
        filters = payload.get('filters')
        if isinstance(filters, dict):
            lines.extend(self._build_gen_filter_lines(filters))

        page_payload = payload.get('page')
        if isinstance(page_payload, dict):
            rows = page_payload.get('rows', [])
            lines.append(
                'page: '
                f'{page_payload.get("pageNum", "-")}/{page_payload.get("pages", "-")} '
                f'(page_size={page_payload.get("pageSize", "-")}, total={page_payload.get("total", "-")})'
            )
            lines.append(f'count: {len(rows) if isinstance(rows, list) else 0}')
            if not isinstance(rows, list) or not rows:
                lines.append('items: none')
                return '\n'.join(lines)
            lines.append('items:')
            for row in rows:
                if isinstance(row, dict):
                    item_lines = (
                        self._build_gen_db_table_item_lines(row) if db_mode else self._build_gen_table_item_lines(row)
                    )
                    lines.extend([f'  {item}' for item in item_lines])
            return '\n'.join(lines)

        items = payload.get('items')
        lines.append(f'count: {payload.get("count", 0)}')
        if not isinstance(items, list) or not items:
            lines.append('items: none')
            return '\n'.join(lines)

        lines.append('items:')
        for item in items:
            if isinstance(item, dict):
                item_lines = (
                    self._build_gen_db_table_item_lines(item) if db_mode else self._build_gen_table_item_lines(item)
                )
                lines.extend([f'  {line}' for line in item_lines])
        return '\n'.join(lines)

    def build_gen_detail_text(self, payload: dict[str, object]) -> str:
        """
        将代码生成业务表详情渲染为文本摘要。

        :param payload: 详情结果字典
        :return: 文本摘要
        """
        detail = payload.get('detail')
        if not isinstance(detail, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'table_id: {payload.get("tableId", "-")}',
                    'detail: none',
                ]
            )

        info = detail.get('info')
        if not isinstance(info, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'table_id: {payload.get("tableId", "-")}',
                    'info: none',
                ]
            )

        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'table_id: {payload.get("tableId", "-")}',
                f'table_name: {payload.get("tableName", "-")}',
                f'column_count: {payload.get("columnCount", 0)}',
                f'table_count: {payload.get("tableCount", 0)}',
                f'table_comment: {SHELL_TEXT_FORMATTER.truncate_text(info.get("tableComment", ""), 80) or "-"}',
                f'class_name: {info.get("className", "-")}',
                f'tpl_category: {info.get("tplCategory", "-")}',
                f'tpl_web_type: {info.get("tplWebType", "-")}',
                f'package_name: {SHELL_TEXT_FORMATTER.truncate_text(info.get("packageName", ""), 80) or "-"}',
                f'module_name: {info.get("moduleName", "-")}',
                f'business_name: {info.get("businessName", "-")}',
                f'function_name: {info.get("functionName", "-")}',
                f'function_author: {info.get("functionAuthor", "-")}',
                f'gen_type: {info.get("genType", "-")}',
                f'gen_path: {SHELL_TEXT_FORMATTER.truncate_text(info.get("genPath", ""), 120) or "-"}',
                f'remark: {SHELL_TEXT_FORMATTER.truncate_text(info.get("remark", ""), 160) or "-"}',
            ]
        )

    @staticmethod
    def _build_text_block(title: str, value: object) -> list[str]:
        """
        将多行文本构建为带标题的块级文本。

        :param title: 块标题
        :param value: 原始文本值
        :return: 文本行列表
        """
        text = '' if value is None else str(value)
        if not text.strip():
            return [f'{title}: -']
        return [f'{title}:', '  |', *[f'    {line}' for line in text.splitlines()]]

    @staticmethod
    def _build_gen_filter_lines(filters: dict[str, object]) -> list[str]:
        """
        构建代码生成表过滤条件文本行。

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
    def _build_gen_table_item_lines(table_item: dict[str, object]) -> list[str]:
        """
        构建单条代码生成表记录的文本行。

        :param table_item: 代码生成表记录
        :return: 文本行列表
        """
        return [
            f'- [{table_item.get("tableId", "-")}] {SHELL_TEXT_FORMATTER.truncate_text(table_item.get("tableName", ""), 40) or "-"}',
            f'  comment: {SHELL_TEXT_FORMATTER.truncate_text(table_item.get("tableComment", ""), 60) or "-"}',
            f'  class_name: {table_item.get("className", "-")}',
            f'  tpl_category: {table_item.get("tplCategory", "-")} | module_name: {table_item.get("moduleName", "-")}',
            f'  business_name: {table_item.get("businessName", "-")} | function_name: {table_item.get("functionName", "-")}',
        ]

    @staticmethod
    def _build_gen_db_table_item_lines(table_item: dict[str, object]) -> list[str]:
        """
        构建单条数据库物理表记录的文本行。

        :param table_item: 数据库物理表记录
        :return: 文本行列表
        """
        return [
            f'- {SHELL_TEXT_FORMATTER.truncate_text(table_item.get("tableName", ""), 48) or "-"}',
            f'  comment: {SHELL_TEXT_FORMATTER.truncate_text(table_item.get("tableComment", ""), 80) or "-"}',
            f'  create_time: {table_item.get("createTime", "-")}',
            f'  update_time: {table_item.get("updateTime", "-")}',
        ]
