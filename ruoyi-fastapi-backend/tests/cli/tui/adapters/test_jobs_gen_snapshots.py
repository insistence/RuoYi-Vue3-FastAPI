from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_collect_jobs_page_snapshot_links_first_job_detail_and_logs(
    monkeypatch: MonkeyPatch,
    jobs_adapter: ModuleType,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        calls.append(arguments)
        if arguments[0:2] == ('job', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'jobId': 101,
                                'jobName': '同步任务',
                                'status': '0',
                                'cronExpression': '0/30 * * * * ?',
                            }
                        ]
                    },
                }
            )
        if arguments[0:2] == ('job', 'detail'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'job': {
                        'jobId': 101,
                        'jobName': '同步任务',
                        'jobGroup': 'DEFAULT',
                        'status': '0',
                        'cronExpression': '0/30 * * * * ?',
                        'invokeTarget': 'demo.sync',
                    },
                }
            )
        if arguments[0:2] == ('job', 'logs') and '--status=1' in arguments:
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'jobLogId': 2,
                                'jobName': '同步任务',
                                'status': '1',
                                'jobMessage': '执行失败',
                                'exceptionInfo': 'traceback...',
                                'createTime': '2026-04-30 10:01:00',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'page': {
                    'rows': [
                        {
                            'jobLogId': 1,
                            'jobName': '同步任务',
                            'status': '0',
                            'jobMessage': '执行成功',
                            'createTime': '2026-04-30 10:00:00',
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(jobs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = jobs_adapter.JOBS_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '任务'
    assert (
        snapshot.subtitle
        == '聚焦：失败聚合 / 暂停任务 / 执行轨迹 | 当前筛选：全部，已匹配 1 条任务，失败任务 1 个，暂停任务 0 个'
    )
    assert len(snapshot.records) == 1
    assert snapshot.records[0].title == '同步任务'
    assert snapshot.shared_sections[0].title == '总览判断'
    assert any('存在失败任务' in line for line in snapshot.shared_sections[0].lines)
    assert any('失败任务: 1 个' in line for line in snapshot.shared_sections[0].lines)
    assert snapshot.shared_sections[1].title == '失败聚合'
    assert any('失败日志: 1 条' in line for line in snapshot.shared_sections[1].lines)
    assert any('同步任务 · 1 次' in line for line in snapshot.shared_sections[1].lines)
    detail_sections = snapshot.records[0].resolve_detail_sections()
    assert [section.title for section in detail_sections] == [
        '任务摘要',
        '调度配置',
        '执行摘要',
        '最近执行记录',
        '失败执行记录',
    ]
    assert any('成功率信号:' in line for line in detail_sections[2].lines)
    assert any('最近一次执行:' in line for line in detail_sections[2].lines)
    assert any('执行轨道:' in line for line in detail_sections[2].lines)
    assert any('轨道窗口:' in line for line in detail_sections[2].lines)
    assert any('2026-04-30 10:00:00' in line for line in detail_sections[3].lines)
    assert any('o 状态: 成功' in line for line in detail_sections[3].lines)
    assert any('轨道: ├─采集  ├─执行  └─落盘' in line for line in detail_sections[3].lines)
    assert any('轨迹: ●─●─◎' in line for line in detail_sections[3].lines)
    assert any('异常: traceback...' in line for line in detail_sections[4].lines)
    assert any(call[0:2] == ('job', 'detail') for call in calls)
    assert any(call[0:2] == ('job', 'logs') and '--job-name=同步任务' in call for call in calls)
    assert any(call[0:2] == ('job', 'logs') and '--status=1' in call for call in calls)


def test_collect_jobs_page_snapshot_applies_failed_filter(
    monkeypatch: MonkeyPatch,
    jobs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('job', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'jobId': 101,
                                'jobName': '失败任务',
                                'status': '0',
                                'cronExpression': '0/30 * * * * ?',
                            },
                            {
                                'jobId': 102,
                                'jobName': '暂停任务',
                                'status': '1',
                                'cronExpression': '0/45 * * * * ?',
                            },
                            {
                                'jobId': 103,
                                'jobName': '正常任务',
                                'status': '0',
                                'cronExpression': '0/50 * * * * ?',
                            },
                        ]
                    },
                }
            )
        if arguments[0:2] == ('job', 'logs') and '--status=1' in arguments:
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'jobLogId': 2,
                                'jobName': '失败任务',
                                'status': '1',
                                'jobMessage': '执行失败',
                                'createTime': '2026-04-30 10:01:00',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': True, 'page': {'rows': []}})

    monkeypatch.setattr(jobs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = jobs_adapter.JOBS_BROWSER_ADAPTER.collect_snapshot('dev', filter_key='failed')

    assert snapshot.active_filter_key == 'failed'
    assert [option.key for option in snapshot.filters] == ['all', 'failed', 'paused', 'ok']
    assert len(snapshot.records) == 1
    assert snapshot.records[0].title == '失败任务'
    assert '当前筛选：失败' in snapshot.subtitle
    assert snapshot.shared_sections[0].title == '总览判断'
    assert any('当前筛选: 失败' in line for line in snapshot.shared_sections[0].lines)
    assert snapshot.shared_sections[1].title == '失败聚合'
    assert any('涉及任务: 1 个' in line for line in snapshot.shared_sections[1].lines)
    assert snapshot.search is not None
    assert snapshot.search.placeholder == '按任务名搜索'


def test_collect_jobs_page_snapshot_applies_query_filter(
    monkeypatch: MonkeyPatch,
    jobs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('job', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'jobId': 1,
                                'jobName': 'sync-user',
                                'jobGroup': 'default',
                                'status': '0',
                                'cronExpression': '*',
                            },
                            {
                                'jobId': 2,
                                'jobName': 'clean-cache',
                                'jobGroup': 'ops',
                                'status': '0',
                                'cronExpression': '*',
                            },
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': True, 'page': {'rows': []}})

    monkeypatch.setattr(jobs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = jobs_adapter.JOBS_BROWSER_ADAPTER.collect_snapshot('dev', query='sync')

    assert [record.title for record in snapshot.records] == ['sync-user']
    assert snapshot.search is not None
    assert snapshot.search.query == 'sync'


def test_collect_jobs_page_snapshot_surfaces_failure_message(
    monkeypatch: MonkeyPatch,
    jobs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del arguments, parse_json
        return SimpleNamespace(
            payload={
                'ok': False,
                'message': '读取定时任务列表失败',
                'error': 'database unavailable',
            }
        )

    monkeypatch.setattr(jobs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = jobs_adapter.JOBS_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.subtitle.startswith('任务数据不可用：')
    assert snapshot.records[0].status == 'fail'
    assert any('读取定时任务列表失败' in line for line in snapshot.records[0].detail_sections[0].lines)


def test_collect_gen_page_snapshot_links_first_table_detail(
    monkeypatch: MonkeyPatch,
    gen_adapter: ModuleType,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        calls.append(arguments)
        if arguments[0:2] == ('gen', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'tableId': 201,
                                'tableName': 'sys_user',
                                'className': 'SysUser',
                                'moduleName': 'system',
                            }
                        ]
                    },
                }
            )
        if arguments[0:2] == ('gen', 'detail'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'tableId': 201,
                    'tableName': 'sys_user',
                    'columnCount': 12,
                    'detail': {
                        'info': {
                            'className': 'SysUser',
                            'moduleName': 'system',
                            'businessName': 'user',
                            'functionName': '用户管理',
                        },
                        'rows': [
                            {
                                'columnName': 'user_id',
                                'columnType': 'bigint',
                                'isPk': '1',
                                'isRequired': '1',
                                'queryType': 'EQ',
                            }
                        ],
                    },
                }
            )
        if arguments[0:2] == ('gen', 'preview'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'tableId': 201,
                    'templateCount': 2,
                    'preview': {
                        'api.py.vm': 'def list_users():\n    return []',
                        'index.vue.vm': '<template>\n  <div />\n</template>',
                    },
                }
            )
        if arguments[0:2] == ('gen', 'export'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'env': 'dev',
                    'mode': 'zip',
                    'dryRun': True,
                    'message': '代码导出预演完成',
                    'tableNames': ['sys_user'],
                    'results': [
                        {
                            'tableName': 'sys_user',
                            'ok': True,
                            'message': '已生成 6 份模板预演结果',
                        }
                    ],
                }
            )
        if arguments[0:2] == ('gen', 'db-list') and '--table-name=sys_user' in arguments:
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'tableName': 'sys_user',
                                'tableComment': '用户表',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'page': {
                    'rows': [
                        {
                            'tableName': 'sys_role',
                            'tableComment': '角色表',
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(gen_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = gen_adapter.GEN_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '代码生成'
    assert (
        snapshot.subtitle
        == '聚焦：生成前校验 / 同步预检查 / 代码预览 | 当前已匹配 1 张业务表，可导入物理表 1 张，可继续查看表定义、预检查和代码预览'
    )
    assert len(snapshot.records) == 1
    assert snapshot.records[0].title == 'sys_user'
    detail_sections = snapshot.records[0].resolve_detail_sections()
    assert [section.title for section in detail_sections] == [
        '业务表摘要',
        '生成配置',
        '字段摘要',
        '生成前校验',
        '同步预检查',
        '字段列表',
        '代码预览',
        '导出预览',
        '导出入口',
    ]
    assert any('模板预览: 2 份' in line for line in detail_sections[3].lines)
    assert any('数据库物理表: sys_user' in line for line in detail_sections[4].lines)
    assert any('模板数量: 2' in line for line in detail_sections[6].lines)
    assert any('api.py.vm' in line for line in detail_sections[6].lines)
    assert any('代码导出预演完成' in line for line in detail_sections[7].lines)
    assert any('wizard gen-export' in line for line in detail_sections[8].lines)
    assert snapshot.shared_sections[0].title == '总览判断'
    assert any('可导入物理表: 1 张' in line for line in snapshot.shared_sections[0].lines)
    assert any('代码预览 / 导出预览 / 导入入口 / 建表入口' in line for line in snapshot.shared_sections[0].lines)
    assert snapshot.shared_sections[1].title == '可导入数据表'
    assert snapshot.shared_sections[2].title == '导入入口'
    assert any(
        'gen import-table sys_role --dry-run --output=text' in line for line in snapshot.shared_sections[2].lines
    )
    assert snapshot.shared_sections[3].title == '建表入口'
    assert any('gen create-table --dry-run --sql' in line for line in snapshot.shared_sections[3].lines)
    assert any(call[0:2] == ('gen', 'detail') for call in calls)
    assert any(call[0:2] == ('gen', 'preview') for call in calls)
    assert any(call[0:2] == ('gen', 'export') and '--dry-run' in call for call in calls)
    assert any(call[0:2] == ('gen', 'db-list') and '--table-name=sys_user' in call for call in calls)


def test_gen_browser_adapter_collect_snapshot_exposes_search_context(
    monkeypatch: MonkeyPatch,
    gen_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('gen', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'tableId': 201,
                                'tableName': 'sys_user',
                                'className': 'SysUser',
                                'moduleName': 'system',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': True, 'page': {'rows': []}})

    monkeypatch.setattr(gen_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = gen_adapter.GEN_BROWSER_ADAPTER.collect_snapshot('dev', query='sys')

    assert snapshot.title == '代码生成'
    assert snapshot.search is not None
    assert snapshot.search.query == 'sys'
    assert snapshot.records
    assert snapshot.records[0].title == 'sys_user'
