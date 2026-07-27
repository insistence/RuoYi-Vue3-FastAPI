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
    expected_menu_ids = ('119', '1061', '1062', '1063', '1064')

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
        ):
            assert expected_text in sql_content
        for menu_id in expected_menu_ids:
            expected_insert = f'insert into sys_role_menu values ({quote}2{quote}, {quote}{menu_id}{quote});'
            assert expected_insert in sql_content


def test_builtin_sql_excludes_ai_plugin_content() -> None:
    """校验 AI 插件内容已迁出系统初始化 SQL。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        for excluded_text in (
            'AI 管理',
            'plugin/ai/model/index',
            'plugin/ai/chat/index',
            'ai_provider_type',
            'create table ai_models',
            'create table ai_chat_config',
        ):
            assert excluded_text not in sql_content


def test_builtin_sql_uses_ordered_plugin_operation_dict_ids() -> None:
    """校验内置 SQL 中插件操作类型字典 ID 已顺序整理。"""
    for sql_path, _quote in SQL_FILES:
        sql_content = read_sql(sql_path)
        assert "insert into sys_dict_type values(12, '插件操作类型', 'plugin_operation_type'" in sql_content
        for dict_code in range(33, 48):
            assert f'insert into sys_dict_data values({dict_code},' in sql_content
