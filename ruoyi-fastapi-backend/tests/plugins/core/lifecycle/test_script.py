from pathlib import Path

import pytest

from plugins.core.lifecycle.script import PluginLifecycleScriptHelper


def test_lifecycle_script_helper_splits_sql_statements() -> None:
    """校验生命周期脚本工具可以拆分 SQL 语句并跳过行注释。"""
    statements = PluginLifecycleScriptHelper.split_sql_statements(
        """
-- create table
create table demo(id int);

insert into demo(id)
values (1);
"""
    )

    assert statements == ['create table demo(id int)', 'insert into demo(id)\nvalues (1)']


def test_lifecycle_script_helper_rejects_delimiter_sql() -> None:
    """校验生命周期脚本工具拒绝 DELIMITER 复杂 SQL 脚本。"""
    with pytest.raises(RuntimeError, match='暂不支持 DELIMITER'):
        PluginLifecycleScriptHelper.split_sql_statements(
            """
DELIMITER //
CREATE PROCEDURE demo_proc()
BEGIN
  SELECT 1;
END //
DELIMITER ;
"""
        )


def test_lifecycle_script_helper_keeps_semicolon_inside_string_literal() -> None:
    """校验 SQL 字符串字面量中的分号不会被当作语句结束符。"""
    statements = PluginLifecycleScriptHelper.split_sql_statements(
        """
insert into demo(message, quoted)
values ('hello;world', 'can''t split');

update demo
set message = "a;b";
"""
    )

    assert statements == [
        "insert into demo(message, quoted)\nvalues ('hello;world', 'can''t split')",
        'update demo\nset message = "a;b"',
    ]


def test_lifecycle_script_helper_filters_database_dialect_paths() -> None:
    """校验生命周期脚本工具按数据库方言过滤路径。"""
    paths = [
        'migrations/mysql/001_init.sql',
        'migrations/postgresql/001_init.sql',
        'migrations/common.sql',
        'other/mysql/ignored.sql',
    ]

    filtered_paths = PluginLifecycleScriptHelper.filter_current_database_paths(
        paths,
        root_dir='migrations',
        database_type='mysql',
    )

    assert filtered_paths == [
        'migrations/mysql/001_init.sql',
        'migrations/common.sql',
        'other/mysql/ignored.sql',
    ]


def test_lifecycle_script_helper_rejects_escape_path(tmp_path: Path) -> None:
    """校验生命周期脚本工具拒绝越过插件根目录的路径。"""
    plugin_root = tmp_path / 'plugins' / 'demo'
    plugin_root.mkdir(parents=True)
    escaped_file = tmp_path / 'outside.sql'
    escaped_file.write_text('select 1;\n', encoding='utf-8')

    with pytest.raises(RuntimeError, match='路径不能越过插件根目录'):
        PluginLifecycleScriptHelper.resolve_file(
            plugin_root,
            '../../outside.sql',
            supported_suffixes={'.sql'},
            label='seed',
        )


def test_lifecycle_script_helper_builds_module_name(tmp_path: Path) -> None:
    """校验生命周期脚本工具构建插件模块名。"""
    plugin_root = tmp_path / 'plugins' / 'demo'
    script_file = plugin_root / 'migrations' / '001_init.py'
    script_file.parent.mkdir(parents=True)
    script_file.write_text('async def run(query_db):\n    return None\n', encoding='utf-8')

    module_name = PluginLifecycleScriptHelper.build_module_name('demo', plugin_root, script_file)

    assert module_name == 'plugins.demo.migrations.001_init'
