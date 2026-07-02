from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MYSQL_SQL = BACKEND_ROOT / 'sql' / 'ruoyi-fastapi.sql'
POSTGRES_SQL = BACKEND_ROOT / 'sql' / 'ruoyi-fastapi-pg.sql'


def read_sql(sql_path: Path) -> str:
    """
    读取初始化 SQL 文件内容。

    :param sql_path: SQL 文件路径
    :return: SQL 文件文本内容
    """
    return sql_path.read_text(encoding='utf-8')


def assert_plugin_management_menu(sql_content: str) -> None:
    """
    校验初始化 SQL 包含插件管理菜单和权限。

    :param sql_content: SQL 文件文本内容
    :return: None
    """
    assert '插件管理' in sql_content
    assert 'system/plugin/index' in sql_content
    assert 'system:plugin:list' in sql_content
    assert 'system:plugin:query' in sql_content
    assert 'system:plugin:edit' in sql_content


def assert_plugin_management_role_menu(sql_content: str, quote: str) -> None:
    """
    校验初始化 SQL 为普通角色绑定插件管理菜单。

    :param sql_content: SQL 文件文本内容
    :param quote: 菜单 ID 是否使用引号
    :return: None
    """
    expected_menu_ids = ('119', '1061', '1062', '1063', '1064')
    for menu_id in expected_menu_ids:
        assert f'insert into sys_role_menu values ({quote}2{quote}, {quote}{menu_id}{quote});' in sql_content


def assert_plugin_tables(sql_content: str) -> None:
    """
    校验初始化 SQL 包含插件系统表。

    :param sql_content: SQL 文件文本内容
    :return: None
    """
    assert 'create table sys_plugin' in sql_content
    assert 'create table sys_plugin_menu' in sql_content
    assert 'uk_sys_plugin_menu_key' in sql_content
    assert 'create table sys_plugin_migration' in sql_content
    assert 'migration_checksum' in sql_content
    assert 'attempt_count' in sql_content
    assert 'started_time' in sql_content
    assert 'finished_time' in sql_content


def assert_ai_plugin_content_not_in_builtin_sql(sql_content: str) -> None:
    """
    校验初始化 SQL 不包含 AI 插件专属内容。

    :param sql_content: SQL 文件文本内容
    :return: None
    """
    assert 'AI 管理' not in sql_content
    assert 'plugin/ai/model/index' not in sql_content
    assert 'plugin/ai/chat/index' not in sql_content
    assert 'ai_provider_type' not in sql_content
    assert 'create table ai_models' not in sql_content
    assert 'create table ai_chat_config' not in sql_content


def assert_plugin_operation_dict_ids(sql_content: str) -> None:
    """
    校验插件操作类型字典 ID 保持连续。

    :param sql_content: SQL 文件文本内容
    :return: None
    """
    assert "insert into sys_dict_type values(12, '插件操作类型', 'plugin_operation_type'" in sql_content
    for dict_code in range(33, 48):
        assert f'insert into sys_dict_data values({dict_code},' in sql_content


def test_mysql_sql_contains_plugin_management_menu() -> None:
    """
    校验 MySQL 初始化脚本包含插件管理菜单入口。

    :return: None
    """
    assert_plugin_management_menu(read_sql(MYSQL_SQL))


def test_postgres_sql_contains_plugin_management_menu() -> None:
    """
    校验 PostgreSQL 初始化脚本包含插件管理菜单入口。

    :return: None
    """
    assert_plugin_management_menu(read_sql(POSTGRES_SQL))


def test_mysql_sql_contains_plugin_tables() -> None:
    """
    校验 MySQL 初始化脚本包含插件系统表。

    :return: None
    """
    assert_plugin_tables(read_sql(MYSQL_SQL))


def test_postgres_sql_contains_plugin_tables() -> None:
    """
    校验 PostgreSQL 初始化脚本包含插件系统表。

    :return: None
    """
    assert_plugin_tables(read_sql(POSTGRES_SQL))


def test_mysql_sql_binds_plugin_management_menu_to_common_role() -> None:
    """
    校验 MySQL 初始化脚本为普通角色绑定插件管理菜单权限。

    :return: None
    """
    assert_plugin_management_role_menu(read_sql(MYSQL_SQL), "'")


def test_postgres_sql_binds_plugin_management_menu_to_common_role() -> None:
    """
    校验 PostgreSQL 初始化脚本为普通角色绑定插件管理菜单权限。

    :return: None
    """
    assert_plugin_management_role_menu(read_sql(POSTGRES_SQL), '')


def test_builtin_sql_excludes_ai_plugin_content() -> None:
    """
    校验 AI 插件内容已迁出系统初始化 SQL。

    :return: None
    """
    assert_ai_plugin_content_not_in_builtin_sql(read_sql(MYSQL_SQL))
    assert_ai_plugin_content_not_in_builtin_sql(read_sql(POSTGRES_SQL))


def test_builtin_sql_uses_ordered_plugin_operation_dict_ids() -> None:
    """
    校验内置 SQL 中插件操作类型字典 ID 已顺序整理。

    :return: None
    """
    assert_plugin_operation_dict_ids(read_sql(MYSQL_SQL))
    assert_plugin_operation_dict_ids(read_sql(POSTGRES_SQL))
