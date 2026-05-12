from typing import Any

from cli.tui.adapters.base import BaseBrowserAdapter
from cli.tui.adapters.models import (
    TUI_ADAPTER_MODEL_RENDERER,
    BrowserPageSnapshot,
    BrowserRecordSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.diagnostics import TUI_DIAGNOSTIC_SERVICE
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


class GenRenderingSupport:
    """
    代码生成浏览页渲染支持对象。

    该对象负责布尔语义渲染与常见文本辅助逻辑，供分区和记录构建复用。
    """

    @staticmethod
    def render_yes_no(value: object) -> str:
        """
        将常见布尔语义值转换为“是/否”。

        :param value: 原始值
        :return: 中文布尔文本
        """
        normalized = str(value).strip().lower()
        return '是' if normalized in {'1', 'y', 'yes', 'true'} else '否'


class GenSectionBuilder:
    """
    代码生成浏览页分区构建器。

    该构建器负责构建代码生成页共享分区，以及单条业务表详情分区。

    :param page_adapter: 代码生成浏览页适配器
    :param rendering: 代码生成浏览页渲染支持对象
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        rendering: GenRenderingSupport,
    ) -> None:
        """
        初始化代码生成浏览页分区构建器。

        :param page_adapter: 代码生成浏览页适配器
        :param rendering: 代码生成浏览页渲染支持对象
        :return: None
        """
        self.page_adapter = page_adapter
        self.rendering = rendering

    def build_gen_focus_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建业务表概览分区。

        :param payload: `gen detail` JSON 负载
        :return: 分区快照
        """
        detail = payload.get('detail') if isinstance(payload, dict) else None
        info = detail.get('info') if isinstance(detail, dict) else None
        if not isinstance(info, dict):
            return DetailSectionSnapshot(
                title='业务表摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='详情', empty_value='无'),
            )
        return DetailSectionSnapshot(
            title='业务表摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 表身份',
                f'表 ID: {payload.get("tableId", "-")}',
                f'表名: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("tableName", "-"), 40)}',
            ],
        )

    def build_gen_generation_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建代码生成配置分区。

        :param payload: `gen detail` JSON 负载
        :return: 分区快照
        """
        detail = payload.get('detail') if isinstance(payload, dict) else None
        info = detail.get('info') if isinstance(detail, dict) else None
        if not isinstance(info, dict):
            return DetailSectionSnapshot(
                title='生成配置',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='生成配置', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='生成配置',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 生成类信息',
                f'生成类名: {SHELL_TEXT_FORMATTER.truncate_text(info.get("className", "-"), 32)}',
                f'所属模块: {SHELL_TEXT_FORMATTER.truncate_text(info.get("moduleName", "-"), 24)}',
                '',
                '## 业务信息',
                f'业务标识: {SHELL_TEXT_FORMATTER.truncate_text(info.get("businessName", "-"), 24)}',
                f'功能名称: {SHELL_TEXT_FORMATTER.truncate_text(info.get("functionName", "-"), 24)}',
            ],
        )

    def build_gen_column_summary_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建字段概览分区。

        :param payload: `gen detail` JSON 负载
        :return: 分区快照
        """
        detail = payload.get('detail') if isinstance(payload, dict) else None
        rows = detail.get('rows') if isinstance(detail, dict) else None
        if not isinstance(rows, list):
            return DetailSectionSnapshot(
                title='字段摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='字段摘要', empty_value='不可用'
                ),
            )
        row_dicts = [row for row in rows if isinstance(row, dict)]
        primary_key_count = sum(1 for row in row_dicts if self.rendering.render_yes_no(row.get('isPk', '-')) == '是')
        required_count = sum(1 for row in row_dicts if self.rendering.render_yes_no(row.get('isRequired', '-')) == '是')
        return DetailSectionSnapshot(
            title='字段摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 字段规模',
                f'字段总数: {payload.get("columnCount", "-")}',
                f'主键字段: {primary_key_count}',
                f'必填字段: {required_count}',
            ],
        )

    def build_gen_columns_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建业务表字段分区。

        :param payload: `gen detail` JSON 负载
        :return: 分区快照
        """
        detail = payload.get('detail') if isinstance(payload, dict) else None
        rows = detail.get('rows') if isinstance(detail, dict) else None
        if not isinstance(rows, list) or not rows:
            return DetailSectionSnapshot(
                title='字段列表',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='字段', empty_value='无'),
            )
        lines: list[str] = []
        for row in rows[:12]:
            if not isinstance(row, dict):
                continue
            lines.extend(
                [
                    f'## {SHELL_TEXT_FORMATTER.truncate_text(row.get("columnName", "-"), 24)} · {SHELL_TEXT_FORMATTER.truncate_text(row.get("columnType", "-"), 20)}',
                    (
                        f'> 主键: {self.rendering.render_yes_no(row.get("isPk", "-"))} | '
                        f'必填: {self.rendering.render_yes_no(row.get("isRequired", "-"))} | '
                        f'查询: {row.get("queryType", "-")}'
                    ),
                    f'> 说明: {SHELL_TEXT_FORMATTER.truncate_text(row.get("columnComment", "-"), 40)}',
                    '',
                ]
            )
        return DetailSectionSnapshot(
            title='字段列表',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=(lines[:-1] if lines and lines[-1] == '' else lines)
            or TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                empty_label='字段信息',
                empty_value='0 列',
                detail='当前业务表没有可展示的字段信息',
            ),
        )

    def build_gen_precheck_section(
        self,
        detail_payload: dict[str, Any] | None,
        preview_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建代码生成前校验分区。

        :param detail_payload: `gen detail` JSON 负载
        :param preview_payload: `gen preview` JSON 负载
        :return: 分区快照
        """
        detail = detail_payload.get('detail') if isinstance(detail_payload, dict) else None
        info = detail.get('info') if isinstance(detail, dict) else None
        rows = detail.get('rows') if isinstance(detail, dict) and isinstance(detail.get('rows'), list) else []
        preview = preview_payload.get('preview') if isinstance(preview_payload, dict) else None
        preview_templates = preview if isinstance(preview, dict) else {}
        row_dicts = [row for row in rows if isinstance(row, dict)]

        has_class_name = bool(isinstance(info, dict) and str(info.get('className', '') or '').strip())
        has_module_name = bool(isinstance(info, dict) and str(info.get('moduleName', '') or '').strip())
        has_business_name = bool(isinstance(info, dict) and str(info.get('businessName', '') or '').strip())
        has_primary_key = any(self.rendering.render_yes_no(row.get('isPk', '-')) == '是' for row in row_dicts)
        column_count = len(row_dicts)
        template_count = len(preview_templates)

        risk_items: list[str] = []
        if not has_class_name:
            risk_items.append('生成类名缺失')
        if not has_module_name:
            risk_items.append('所属模块缺失')
        if not has_business_name:
            risk_items.append('业务标识缺失')
        if column_count <= 0:
            risk_items.append('字段列表为空')
        if not has_primary_key:
            risk_items.append('未识别到主键字段')
        if template_count <= 0:
            risk_items.append('未生成可预览模板')

        status = 'ok' if not risk_items else 'warn'
        return DetailSectionSnapshot(
            title='生成前校验',
            status=status,
            lines=[
                '## 校验结果',
                f'生成类名: {"通过" if has_class_name else "缺失"}',
                f'所属模块: {"通过" if has_module_name else "缺失"}',
                f'业务标识: {"通过" if has_business_name else "缺失"}',
                f'字段数量: {column_count}',
                f'主键字段: {"通过" if has_primary_key else "缺失"}',
                f'模板预览: {template_count} 份',
                '',
                '## 风险提示',
                *(risk_items if risk_items else ['当前未发现阻断生成的明显风险']),
            ],
        )

    def build_gen_sync_precheck_section(
        self,
        table_name: str,
        payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建数据库表结构同步前检查分区。

        :param table_name: 业务表名称
        :param payload: `gen db-list --table-name=...` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='同步预检查',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='同步预检查', empty_value='不可用'
                ),
            )

        rows = self.page_adapter.extract_page_rows(payload)
        matched_row = next(
            (row for row in rows if str(row.get('tableName', '') or '').strip().lower() == table_name.strip().lower()),
            None,
        )
        if matched_row is None:
            return DetailSectionSnapshot(
                title='同步预检查',
                status='warn',
                lines=[
                    '## 当前状态',
                    f'目标业务表: {table_name}',
                    '数据库物理表: 未匹配',
                    '',
                    '## 建议操作',
                    '当前数据库中未找到同名物理表，执行同步前应先确认表结构来源',
                ],
            )

        return DetailSectionSnapshot(
            title='同步预检查',
            status='ok',
            lines=[
                '## 当前状态',
                f'目标业务表: {table_name}',
                f'数据库物理表: {matched_row.get("tableName", "-")}',
                f'表注释: {SHELL_TEXT_FORMATTER.truncate_text(matched_row.get("tableComment", "-"), 56)}',
                '',
                '## 建议操作',
                '已匹配到同名物理表，可继续使用同步数据库表结构动作',
            ],
        )

    def build_gen_preview_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建代码预览分区。

        :param payload: `gen preview` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='代码预览',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='代码预览', empty_value='不可用'
                ),
            )
        preview_payload = payload.get('preview') if isinstance(payload.get('preview'), dict) else {}
        lines = [
            '## 模板规模',
            f'模板数量: {payload.get("templateCount", len(preview_payload))}',
        ]
        if not preview_payload:
            lines.extend(
                [
                    '',
                    *TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                        empty_label='模板样本',
                        empty_value='0 份',
                        detail='当前业务表没有可预览的模板输出',
                    ),
                ]
            )
            return DetailSectionSnapshot(title='代码预览', status='info', lines=lines)

        lines.extend(['', '## 模板样本'])
        for template_name, template_content in list(preview_payload.items())[:4]:
            preview_lines = str(template_content).splitlines()[:3]
            lines.append(f'## {SHELL_TEXT_FORMATTER.truncate_text(template_name, 48)}')
            lines.extend(f'> {SHELL_TEXT_FORMATTER.truncate_text(line, 72)}' for line in preview_lines)
            lines.append('')
        if lines[-1] == '':
            lines.pop()
        return DetailSectionSnapshot(
            title='代码预览',
            status='ok',
            lines=lines,
        )

    def build_gen_export_preview_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建代码导出预演分区。

        :param payload: `gen export --dry-run` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='导出预览',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='导出预览', empty_value='不可用'
                ),
            )

        results = payload.get('results') if isinstance(payload.get('results'), list) else []
        lines = [
            '## 预演结果',
            f'执行模式: {payload.get("mode", "-")}',
            f'dry-run: {"是" if payload.get("dryRun", False) else "否"}',
            f'表数量: {len(payload.get("tableNames", [])) if isinstance(payload.get("tableNames"), list) else 0}',
            f'结果数量: {len(results)}',
            '',
            '## 摘要',
            f'结果摘要: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("message", "-"), 72)}',
        ]
        if payload.get('outputFile'):
            lines.append(f'输出文件: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("outputFile", "-"), 72)}')
        if payload.get('genPath'):
            lines.append(f'输出目录: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("genPath", "-"), 72)}')
        if results:
            lines.extend(['', '## 结果样本'])
            for item in results[:4]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f'> {item.get("tableName", "-")} · {"成功" if item.get("ok", False) else "失败"} · '
                    f'{SHELL_TEXT_FORMATTER.truncate_text(item.get("message", "-"), 48)}'
                )
        return DetailSectionSnapshot(
            title='导出预览',
            status='ok',
            lines=lines,
        )

    def build_importable_tables_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建数据库可导入表共享分区。

        :param payload: `gen db-list` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='可导入数据表',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='数据表', empty_value='不可用'
                ),
            )
        rows = self.page_adapter.extract_page_rows(payload)
        lines = TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='可导入数据表',
            empty_value='0 张',
            detail='当前环境没有可导入的数据库表',
        )
        if rows:
            lines = [
                f'{SHELL_TEXT_FORMATTER.truncate_text(row.get("tableName", "-"), 40)} · {SHELL_TEXT_FORMATTER.truncate_text(row.get("tableComment", "-"), 48)}'
                for row in rows[:8]
            ]
        return DetailSectionSnapshot(
            title='可导入数据表',
            status='ok',
            lines=lines,
        )

    @staticmethod
    def build_gen_export_entry_section(table_name: str) -> DetailSectionSnapshot:
        """
        构建代码导出向导入口分区。

        :param table_name: 当前业务表名称
        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='导出入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario=f'准备导出当前业务表 {table_name} 的生成结果时，应先通过向导确认目标表、输出目录和覆盖范围。',
                command=TUI_COPY.build_cli_command_hint('wizard', 'gen-export', '--output=text'),
                guide='进入向导后优先选择当前业务表，并在最终确认前检查导出目录和文件覆盖预览。',
            ),
        )

    @staticmethod
    def build_gen_import_entry_section(importable_rows: list[dict[str, Any]]) -> DetailSectionSnapshot:
        """
        构建物理表导入入口分区。

        :param importable_rows: 可导入物理表列表
        :return: 分区快照
        """
        suggested_table_names = [
            str(row.get('tableName', '') or '').strip()
            for row in importable_rows[:3]
            if str(row.get('tableName', '') or '').strip()
        ]
        suggested_tables = ' '.join(suggested_table_names) if suggested_table_names else '<table_name>'
        return DetailSectionSnapshot(
            title='导入入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备把数据库物理表纳入代码生成管理时，应先核对物理表名、注释和目标环境，再通过导入命令执行 dry-run 预演。',
                command=TUI_COPY.build_cli_command_hint(
                    'gen', 'import-table', suggested_tables, '--dry-run', '--output=text'
                ),
                guide='建议先从“可导入数据表”中确认目标表名，必要时一次只导入 1 到 3 张表，确认 dry-run 输出后再执行真实导入。',
            ),
        )

    @staticmethod
    def build_gen_create_entry_section() -> DetailSectionSnapshot:
        """
        构建建表 SQL 导入入口分区。

        :return: 分区快照
        """
        sql_template = 'CREATE TABLE demo_table (id bigint primary key);'
        return DetailSectionSnapshot(
            title='建表入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备根据建表 SQL 直接创建物理表并导入代码生成配置时，应先使用单条 SQL 执行 dry-run 预演，确认语句可解析且只包含目标表。',
                command=TUI_COPY.build_cli_command_hint(
                    'gen', 'create-table', '--dry-run', '--sql', sql_template, '--output=text'
                ),
                guide='建议优先使用单条 CREATE TABLE 语句做预演；若 SQL 较长或来自文件，可改用 --sql-file 方式，但不要同时传入 --sql 与 --sql-file。',
            ),
        )

    def load_gen_detail_sections(
        self,
        table_row: dict[str, Any],
        env: str,
    ) -> list[DetailSectionSnapshot]:
        """
        按需加载单条业务表详情分区。

        :param table_row: 业务表列表行数据
        :param env: 当前运行环境
        :return: 详情分区列表
        """
        table_id = table_row.get('tableId')
        detail_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'detail',
            str(table_id),
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        preview_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'preview',
            str(table_id),
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        table_name = str(table_row.get('tableName', '-') or '-')
        export_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'export',
            table_name,
            f'--env={env}',
            '--dry-run',
            '--mode=zip',
            '--output=json',
            '--yes',
            parse_json=True,
        ).payload
        sync_check_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'db-list',
            f'--env={env}',
            f'--table-name={table_name}',
            '--paged',
            '--page-size=5',
            '--output=json',
            parse_json=True,
        ).payload
        return [
            self.build_gen_focus_section(detail_payload),
            self.build_gen_generation_section(detail_payload),
            self.build_gen_column_summary_section(detail_payload),
            self.build_gen_precheck_section(detail_payload, preview_payload),
            self.build_gen_sync_precheck_section(table_name, sync_check_payload),
            self.build_gen_columns_section(detail_payload),
            self.build_gen_preview_section(preview_payload),
            self.build_gen_export_preview_section(export_payload),
            self.build_gen_export_entry_section(table_name),
        ]

    def build_gen_overview_section(
        self,
        gen_rows: list[dict[str, Any]],
        filtered_rows: list[dict[str, Any]],
        importable_rows: list[dict[str, Any]],
    ) -> DetailSectionSnapshot:
        """
        构建代码生成页总览判断共享分区。

        :param gen_rows: 全量业务表行列表
        :param filtered_rows: 当前筛选后的业务表行列表
        :param importable_rows: 可导入物理表行列表
        :return: 分区快照
        """
        incomplete_count = sum(
            1
            for row in gen_rows
            if not str(row.get('className', '') or '').strip()
            or not str(row.get('moduleName', '') or '').strip()
            or not str(row.get('businessName', '') or '').strip()
        )
        status = 'ok'
        conclusion = '当前生成配置可继续下钻，优先查看预检查、代码预览和导出预演'
        if incomplete_count > 0:
            status = 'warn'
            conclusion = '存在生成配置不完整的业务表，建议先处理生成前校验风险'
        elif not gen_rows and importable_rows:
            status = 'info'
            conclusion = '当前还没有业务表配置，可先从可导入物理表中选择目标'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'已加载业务表: {len(gen_rows)} 张',
                f'当前匹配: {len(filtered_rows)} 张',
                f'可导入物理表: {len(importable_rows)} 张',
                f'配置待补全: {incomplete_count} 张',
                '',
                '## 建议入口',
                '优先关注：生成前校验 / 同步预检查 / 代码预览 / 导出预览 / 导入入口 / 建表入口',
            ],
        )


class GenRecordBuilder:
    """
    代码生成浏览记录构建器。

    该对象负责构建代码生成页单条业务表浏览记录与失败兜底记录。

    :param page_adapter: 代码生成浏览页适配器
    :param section_builder: 代码生成浏览页分区构建器
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        section_builder: GenSectionBuilder,
    ) -> None:
        """
        初始化代码生成浏览记录构建器。

        :param page_adapter: 代码生成浏览页适配器
        :param section_builder: 代码生成浏览页分区构建器
        :return: None
        """
        self.page_adapter = page_adapter
        self.section_builder = section_builder

    def build_gen_record(self, table_row: dict[str, Any], env: str) -> BrowserRecordSnapshot:
        """
        构建单条业务表浏览记录。

        :param table_row: 业务表列表行数据
        :param env: 当前运行环境
        :return: 浏览记录快照
        """
        table_id = table_row.get('tableId', '-')
        table_name = str(table_row.get('tableName', '-') or '-')
        class_name = str(table_row.get('className', '-') or '-')
        module_name = str(table_row.get('moduleName', '-') or '-')

        return BrowserRecordSnapshot(
            key=f'gen:{table_id}',
            title=SHELL_TEXT_FORMATTER.truncate_text(table_name, 40),
            status='ok',
            summary=f'生成类 {SHELL_TEXT_FORMATTER.truncate_text(class_name, 24)} · 模块 {SHELL_TEXT_FORMATTER.truncate_text(module_name, 20)}',
            metadata_lines=[
                '## 表身份',
                f'表 ID: {table_id}',
                '',
                '## 生成信息',
                f'生成类名: {SHELL_TEXT_FORMATTER.truncate_text(class_name, 32)}',
                f'所属模块: {SHELL_TEXT_FORMATTER.truncate_text(module_name, 24)}',
                f'业务标识: {SHELL_TEXT_FORMATTER.truncate_text(table_row.get("businessName", "-"), 24)}',
            ],
            detail_sections=[],
            detail_loader=lambda table_row=table_row, env=env: self.section_builder.load_gen_detail_sections(
                table_row, env
            ),
        )

    def build_failure_record(self, payload: dict[str, Any] | None) -> BrowserRecordSnapshot:
        """
        构建代码生成页失败兜底记录。

        :param payload: 失败结果负载
        :return: 浏览记录快照
        """
        return self.page_adapter.build_failure_record(
            key='gen:unavailable',
            subject='代码生成',
            section_subject='业务表列表',
            payload=payload,
        )


class GenBrowserAdapter(BaseBrowserAdapter):
    """
    代码生成浏览页适配器。

    该适配器负责采集业务表列表、详情、预览与可导入表清单，并委托
    协作对象完成共享分区、详情分区和记录构建。
    """

    def __init__(
        self,
        rendering: GenRenderingSupport | None = None,
        section_builder: GenSectionBuilder | None = None,
        record_builder: GenRecordBuilder | None = None,
    ) -> None:
        """
        初始化代码生成浏览页适配器。

        :param rendering: 代码生成浏览页渲染支持对象
        :param section_builder: 代码生成浏览页分区构建器
        :param record_builder: 代码生成浏览记录构建器
        :return: None
        """
        super().__init__(
            page_title='代码生成',
            search_view_key='gen',
            filter_options=(),
        )
        self.rendering = rendering or GenRenderingSupport()
        self.section_builder = section_builder or GenSectionBuilder(self, self.rendering)
        self.record_builder = record_builder or GenRecordBuilder(self, self.section_builder)

    @staticmethod
    def apply_gen_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """
        按业务表名、生成类名或模块名查询词过滤业务表行数据。

        :param rows: 原始业务表行列表
        :param query: 当前搜索词
        :return: 过滤后的业务表行列表
        """
        normalized_query = str(query).strip().lower()
        if not normalized_query:
            return rows
        return [
            row
            for row in rows
            if normalized_query in str(row.get('tableName', '') or '').strip().lower()
            or normalized_query in str(row.get('className', '') or '').strip().lower()
            or normalized_query in str(row.get('moduleName', '') or '').strip().lower()
        ]

    def collect_snapshot(self, env: str, query: str = '') -> BrowserPageSnapshot:
        """
        采集代码生成浏览页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 浏览页快照
        """
        search_context = self.resolve_search_context(query)
        gen_tables_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'list',
            f'--env={env}',
            '--paged',
            '--page-size=8',
            '--output=json',
            parse_json=True,
        ).payload
        db_tables_payload = NESTED_CLI_SUPPORT.run(
            'gen',
            'db-list',
            f'--env={env}',
            '--paged',
            '--page-size=8',
            '--output=json',
            parse_json=True,
        ).payload
        importable_rows = self.extract_page_rows(db_tables_payload)

        if not isinstance(gen_tables_payload, dict) or not gen_tables_payload.get('ok', False):
            return BrowserPageSnapshot(
                title='代码生成',
                subtitle=TUI_COPY.build_unavailable_subtitle(
                    '业务表',
                    SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(gen_tables_payload), 72),
                ),
                records=[self.record_builder.build_failure_record(gen_tables_payload)],
                shared_sections=[
                    self.section_builder.build_gen_overview_section([], [], importable_rows),
                    self.section_builder.build_importable_tables_section(db_tables_payload),
                    self.section_builder.build_gen_import_entry_section(importable_rows),
                    self.section_builder.build_gen_create_entry_section(),
                ],
                search=search_context,
            )

        rows = self.extract_page_rows(gen_tables_payload)
        filtered_rows = self.apply_gen_query(rows, query)
        records = [self.record_builder.build_gen_record(table_row, env) for table_row in filtered_rows[:8]]
        if not records:
            records = [
                self.build_empty_record(
                    key='gen:none',
                    subject='业务表',
                    empty_label='业务表',
                    has_source_rows=bool(rows),
                    filtered_summary='当前搜索条件下没有匹配业务表',
                    empty_summary='当前环境中还没有纳入代码生成的业务表',
                    filtered_empty_value='暂无匹配',
                    empty_empty_value='暂无配置',
                    filtered_detail='当前搜索条件下没有匹配业务表',
                    empty_detail='当前环境中尚未配置代码生成业务表',
                )
            ]

        return BrowserPageSnapshot(
            title='代码生成',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_gen_diagnostic_subtitle(
                len(filtered_rows),
                len(importable_rows),
            ),
            records=records,
            shared_sections=[
                self.section_builder.build_gen_overview_section(rows, filtered_rows, importable_rows),
                self.section_builder.build_importable_tables_section(db_tables_payload),
                self.section_builder.build_gen_import_entry_section(importable_rows),
                self.section_builder.build_gen_create_entry_section(),
            ],
            search=search_context,
        )


GEN_BROWSER_ADAPTER = GenBrowserAdapter()
