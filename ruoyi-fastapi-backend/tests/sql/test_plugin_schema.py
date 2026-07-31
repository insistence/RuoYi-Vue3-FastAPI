from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SQL_FILES = (
    (BACKEND_ROOT / 'sql' / 'ruoyi-fastapi.sql', "'"),
    (BACKEND_ROOT / 'sql' / 'ruoyi-fastapi-pg.sql', ''),
)


def read_sql(sql_path: Path) -> str:
    """读取初始化 SQL 文件内容。"""
    return sql_path.read_text(encoding='utf-8')


def test_builtin_sql_contains_plugin_schema_and_management_permissions() -> None:
    """校验内置 SQL 包含插件表结构与管理权限。"""
    expected_menu_ids = ('120', '1069', '1070', '1071', '1072')

    for sql_path, quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        for expected_text in (
            '插件管理',
            'system/plugin/index',
            'system:plugin:list',
            'system:plugin:query',
            'system:plugin:edit',
            'create table sys_plugin',
            'create table sys_plugin_menu',
            'uk_sys_plugin_menu_key',
            'create table sys_plugin_migration',
            'migration_checksum',
            'attempt_count',
            'started_time',
            'finished_time',
            'ck_sys_plugin_enabled',
            'ck_sys_plugin_status',
        ):
            assert expected_text in sql_content
        for menu_id in expected_menu_ids:
            expected_insert = f'insert into sys_role_menu values ({quote}2{quote}, {quote}{menu_id}{quote});'
            assert expected_insert in sql_content


def test_file_and_plugin_management_menu_ids_are_contiguous() -> None:
    """校验文件管理及插件管理菜单编号连续且父子关系正确。"""
    file_permissions = (
        'system:file:query',
        'system:file:download',
        'system:file:remove',
        'system:file:edit',
        'system:file:transfer',
        'system:file:restore',
        'system:file:purge',
        'system:file:reconcile',
    )
    plugin_permissions = (
        'system:plugin:query',
        'system:plugin:edit',
        'system:plugin:list',
        'system:plugin:export',
    )

    for sql_path, quote in SQL_FILES:
        sql_lines = read_sql(sql_path).splitlines()
        file_menu_line = next(line for line in sql_lines if "'文件管理'" in line)
        plugin_menu_line = next(line for line in sql_lines if "'插件管理'" in line)
        assert f'values({quote}119{quote},' in file_menu_line
        assert f'values({quote}120{quote},' in plugin_menu_line

        for menu_id, permission in enumerate(file_permissions, start=1061):
            permission_line = next(line for line in sql_lines if f"'{permission}'" in line and "'F'" in line)
            assert f'values({quote}{menu_id}{quote},' in permission_line
            assert f', {quote}119{quote},' in permission_line
        for menu_id in (119, *range(1061, 1069)):
            expected_insert = f'insert into sys_role_menu values ({quote}2{quote}, {quote}{menu_id}{quote});'
            assert expected_insert in sql_lines

        for menu_id, permission in enumerate(plugin_permissions, start=1069):
            permission_line = next(line for line in sql_lines if f"'{permission}'" in line and "'F'" in line)
            assert f'values({quote}{menu_id}{quote},' in permission_line
            assert f', {quote}120{quote},' in permission_line


def test_builtin_sql_excludes_ai_plugin_content_and_preserves_file_management() -> None:
    """校验 AI 内容由插件管理，同时保留上游文件管理初始化内容。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        for excluded_text in (
            'AI 管理',
            'ai/model/index',
            'ai/chat/index',
            'plugin/ai/model/index',
            'plugin/ai/chat/index',
            'ai_provider_type',
            'create table ai_models',
            'create table ai_chat_config',
        ):
            assert excluded_text not in sql_content
        for expected_text in (
            '文件管理',
            'system/file/index',
            'create table sys_file_info',
            'create table sys_file_reconcile_issue',
        ):
            assert expected_text in sql_content
        assert '-- 21、文件信息表' in sql_content
        assert '-- 28、文件存储对账异常表' in sql_content
        assert '-- 29、插件信息表' in sql_content
        assert '-- 33、插件批量操作审计日志表' in sql_content
        assert sql_content.index('create table sys_file_info') < sql_content.index('create table sys_plugin')


def test_builtin_sql_contains_notice_read_schema() -> None:
    """校验内置 SQL 包含公告已读记录表及唯一约束。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        assert 'create table sys_notice_read' in sql_content
        assert 'uk_user_notice' in sql_content
        assert sql_content.index('create table sys_notice') < sql_content.index('create table sys_notice_read')


def test_builtin_sql_contains_password_character_type_config() -> None:
    """校验内置 SQL 包含密码字符范围参数，且不与已有配置 ID 冲突。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        config_line = next(line for line in sql_content.splitlines() if "'sys.account.chrtype'" in line)
        assert 'values(10,' in config_line
        assert "'0'" in config_line
        assert sql_content.count("'sys.account.chrtype'") == 1


def test_builtin_sql_contains_job_log_execution_time_columns() -> None:
    """校验内置 SQL 的调度日志表使用毫秒精度记录执行时间。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        job_log_schema = sql_content.split('create table sys_job_log', maxsplit=1)[1].split(
            'create table sys_notice',
            maxsplit=1,
        )[0]
        time_type = 'datetime(3)' if sql_path.name == 'ruoyi-fastapi.sql' else 'timestamp(3)'
        assert f'start_time          {time_type}' in job_log_schema or f'start_time {time_type}' in job_log_schema
        assert f'end_time            {time_type}' in job_log_schema or f'end_time {time_type}' in job_log_schema


def test_builtin_sql_uses_ordered_plugin_operation_dict_ids() -> None:
    """校验内置 SQL 中插件操作类型字典 ID 已顺序整理。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        assert "insert into sys_dict_type values(12, '插件操作类型', 'plugin_operation_type'" in sql_content
        for dict_code in range(33, 48):
            assert f'insert into sys_dict_data values({dict_code},' in sql_content
