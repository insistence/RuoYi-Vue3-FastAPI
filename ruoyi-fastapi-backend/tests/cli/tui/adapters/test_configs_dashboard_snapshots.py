from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_collect_dashboard_snapshot_adds_risk_heat_panel(
    monkeypatch: MonkeyPatch,
    health_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('app', 'env'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'runtime': {
                        'cliEnv': 'dev',
                        'configEnv': 'dev',
                        'envFile': '.env.dev',
                        'envFileExists': True,
                    },
                }
            )
        if arguments[0:2] == ('app', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': False,
                    'database': {'ok': False, 'message': '数据库连接失败'},
                    'redis': {'ok': True, 'message': 'Redis 正常'},
                    'crypto': {'ok': True, 'message': '加密组件正常'},
                }
            )
        if arguments[0:2] == ('app', 'routes'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'count': 3,
                    'routes': [],
                    'groupedRoutes': {'system': [{}, {}], 'monitor': [{}]},
                }
            )
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(
                payload={
                    'ok': False,
                    'currentRevision': '-',
                    'message': 'revision unavailable',
                }
            )
        if arguments[0:2] == ('ops', 'deps'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': '核心运行依赖已安装',
                    'missingRequired': [],
                    'packages': {
                        'python': {'installed': True, 'version': '3.10.0'},
                        'fastapi': {'installed': True, 'version': '0.111.0'},
                        'sqlalchemy': {'installed': True, 'version': '2.0.0'},
                        'redis': {'installed': True, 'version': '5.0.0'},
                    },
                }
            )
        if arguments[0:2] == ('ops', 'server-info'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'server': {
                        'sys': {'computerName': 'ruoyi-node', 'computerIp': '10.0.0.8'},
                        'cpu': {'used': 18.2},
                        'mem': {'usage': 42.5},
                    },
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'dbSize': 128,
                'info': {'redis_version': '7.0', 'connected_clients': 12},
                'cacheNames': ['sys_config'],
            }
        )

    monkeypatch.setattr(health_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = health_adapter.DASHBOARD_ADAPTER.collect_snapshot('dev')

    assert any(panel.title == '总览判断' for panel in snapshot.panels)
    assert any(panel.title == '建议摘要' for panel in snapshot.panels)
    assert any(panel.title == '风险摘要' for panel in snapshot.panels)
    assert any(panel.title == '依赖版本' for panel in snapshot.panels)
    assert any(panel.title == '服务器摘要' for panel in snapshot.panels)
    app_panel = next(panel for panel in snapshot.panels if panel.title == '应用摘要')
    conclusion_panel = next(panel for panel in snapshot.panels if panel.title == '总览判断')
    entry_panel = next(panel for panel in snapshot.panels if panel.title == '建议摘要')
    assert any('当前环境: dev | CLI 目标环境: dev' in line for line in app_panel.lines)
    assert any('注册路由: 3 条 | 标签分组: 2 个' in line for line in app_panel.lines)
    assert conclusion_panel.status == 'fail'
    assert any('数据库存在异常' in line for line in conclusion_panel.lines)
    assert any('优先进入数据库页面' in line for line in conclusion_panel.lines)
    assert entry_panel.status == 'fail'
    assert any('[B] 数据库' in line for line in entry_panel.lines)
    assert any('[O] 运维' in line for line in entry_panel.lines)
    assert any('聚焦：迁移版本 / 连接状态 / Heads' in line for line in entry_panel.lines)
    assert any('聚焦：数据库连通性 / Redis 连通性 / 依赖版本' in line for line in entry_panel.lines)
    heat_panel = next(panel for panel in snapshot.panels if panel.title == '风险摘要')
    assert heat_panel.status == 'fail'
    assert any('HOT-01' in line for line in heat_panel.lines)
    assert any(metric.title == '依赖通过率' and '[' in metric.value for metric in snapshot.metrics)


def test_dashboard_adapter_collect_snapshot_exposes_metrics(
    monkeypatch: MonkeyPatch,
    health_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('app', 'env'):
            return SimpleNamespace(payload={'ok': True, 'runtime': {'cliEnv': 'dev', 'configEnv': 'dev'}})
        if arguments[0:2] == ('app', 'routes'):
            return SimpleNamespace(payload={'ok': True, 'count': 2, 'routes': [], 'groupedRoutes': {}})
        if arguments[0:2] == ('app', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'database': {'ok': True, 'message': '数据库正常'},
                    'redis': {'ok': True, 'message': 'Redis 正常'},
                    'crypto': {'ok': True, 'message': '加密正常'},
                }
            )
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(payload={'ok': True, 'currentRevision': '202604300001'})
        if arguments[0:2] == ('ops', 'deps'):
            return SimpleNamespace(payload={'ok': True, 'missingRequired': [], 'packages': {}})
        if arguments[0:2] == ('ops', 'server-info'):
            return SimpleNamespace(payload={'ok': True, 'server': {'sys': {}, 'cpu': {}, 'mem': {}}})
        return SimpleNamespace(payload={'ok': True, 'dbSize': 27, 'info': {}, 'cacheNames': []})

    monkeypatch.setattr(health_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = health_adapter.DASHBOARD_ADAPTER.collect_snapshot('dev')

    assert snapshot.env == 'dev'
    assert snapshot.metrics
    assert any(metric.title == '依赖通过率' for metric in snapshot.metrics)
    assert any(panel.title == '总览判断' for panel in snapshot.panels)


def test_collect_dashboard_snapshot_uses_focus_hints_for_healthy_business_entry(
    monkeypatch: MonkeyPatch,
    health_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('app', 'env'):
            return SimpleNamespace(payload={'ok': True, 'runtime': {'cliEnv': 'dev', 'configEnv': 'dev'}})
        if arguments[0:2] == ('app', 'routes'):
            return SimpleNamespace(
                payload={'ok': True, 'count': 4, 'routes': [], 'groupedRoutes': {'system': [{}, {}]}}
            )
        if arguments[0:2] == ('app', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'database': {'ok': True, 'message': '数据库正常'},
                    'redis': {'ok': True, 'message': 'Redis 正常'},
                    'crypto': {'ok': True, 'message': '加密组件正常'},
                }
            )
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(payload={'ok': True, 'currentRevision': '202604300001'})
        if arguments[0:2] == ('ops', 'deps'):
            return SimpleNamespace(payload={'ok': True, 'missingRequired': [], 'packages': {}, 'message': '依赖正常'})
        if arguments[0:2] == ('ops', 'server-info'):
            return SimpleNamespace(payload={'ok': True, 'server': {'sys': {}, 'cpu': {}, 'mem': {}}})
        return SimpleNamespace(
            payload={
                'ok': True,
                'dbSize': 27,
                'info': {'redis_version': '7.2.6', 'connected_clients': 1},
                'cacheNames': [],
            }
        )

    monkeypatch.setattr(health_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = health_adapter.DASHBOARD_ADAPTER.collect_snapshot('dev')

    entry_panel = next(panel for panel in snapshot.panels if panel.title == '建议摘要')

    assert entry_panel.status == 'ok'
    assert any('聚焦：失败聚合 / 暂停任务 / 执行轨迹' in line for line in entry_panel.lines)
    assert any('聚焦：高风险配置 / 值不一致 / 缓存漂移' in line for line in entry_panel.lines)
    assert any('生成前校验' in line and '代码预览' in line for line in entry_panel.lines)


def test_collect_configs_page_snapshot_surfaces_failure_message(
    monkeypatch: MonkeyPatch,
    configs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del arguments, parse_json
        return SimpleNamespace(
            payload={
                'ok': False,
                'message': '读取参数配置诊断信息失败',
                'error': 'database unavailable',
            }
        )

    monkeypatch.setattr(configs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '参数配置'
    assert snapshot.records[0].status == 'fail'
    assert snapshot.shared_sections[0].title == '总览判断'
    assert snapshot.shared_sections[1].title == '配置巡检'
    assert any('读取参数配置诊断信息失败' in line for line in snapshot.shared_sections[1].lines)
    assert any('database unavailable' in line for line in snapshot.shared_sections[1].lines)


def test_configs_browser_adapter_collect_snapshot_exposes_search_context(
    monkeypatch: MonkeyPatch,
    configs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('config', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'databaseCount': 1,
                    'cacheCount': 1,
                    'missingInCacheCount': 0,
                    'orphanInCacheCount': 0,
                    'mismatchCount': 0,
                    'missingInCache': [],
                    'orphanInCache': [],
                    'mismatchKeys': [],
                }
            )
        if arguments[0:2] == ('config', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'configId': 1,
                                'configKey': 'site_name',
                                'configName': '站点名称',
                                'configType': 'Y',
                                'configValue': 'RuoYi',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': False, 'message': 'unexpected'})

    monkeypatch.setattr(configs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev', query='site')

    assert snapshot.title == '参数配置'
    assert snapshot.search is not None
    assert snapshot.search.query == 'site'
    assert snapshot.records
    assert snapshot.records[0].title == 'site_name'


def test_collect_configs_page_snapshot_builds_browser_records(
    monkeypatch: MonkeyPatch,
    configs_adapter: ModuleType,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        calls.append(arguments)
        if arguments[0:2] == ('config', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'databaseCount': 3,
                    'cacheCount': 3,
                    'missingInCacheCount': 0,
                    'orphanInCacheCount': 0,
                    'mismatchCount': 1,
                    'mismatchKeys': ['site_name'],
                }
            )
        if arguments[0:2] == ('config', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'configId': 1,
                                'configKey': 'site_name',
                                'configName': '站点名称',
                                'configType': 'Y',
                                'configValue': 'RuoYi',
                            }
                        ]
                    },
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'key': 'site_name',
                'source': 'both',
                'inSync': False,
                'database': {
                    'configId': 1,
                    'configKey': 'site_name',
                    'configName': '站点名称',
                    'configValue': 'RuoYi',
                    'configType': 'Y',
                    'remark': '数据库值',
                },
                'cache': {
                    'configId': 1,
                    'configKey': 'site_name',
                    'configName': '站点名称',
                    'configValue': 'RuoYi-Cache',
                    'configType': 'Y',
                    'remark': '缓存值',
                },
            }
        )

    monkeypatch.setattr(configs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '参数配置'
    assert (
        snapshot.subtitle
        == '聚焦：高风险配置 / 值不一致 / 缓存漂移 | 当前筛选：全部，已匹配 1 项配置，值不一致 1 项，缓存漂移 0 项'
    )
    assert snapshot.active_filter_key == 'all'
    assert [option.key for option in snapshot.filters] == ['all', 'risky', 'mismatch', 'cache-drift']
    assert len(snapshot.records) == 1
    assert snapshot.records[0].title == 'site_name'
    assert snapshot.records[0].status == 'fail'
    detail_sections = snapshot.records[0].resolve_detail_sections()
    assert [section.title for section in detail_sections] == ['同步状态', '数据库配置', '缓存配置']
    assert any('数据库与缓存一致: 否' in line for line in detail_sections[0].lines)
    assert any('键值: RuoYi' in line for line in detail_sections[1].lines)
    assert any('键值: RuoYi-Cache' in line for line in detail_sections[2].lines)
    assert snapshot.shared_sections[0].title == '总览判断'
    assert any('值不一致: 1 项' in line for line in snapshot.shared_sections[0].lines)
    assert snapshot.shared_sections[1].title == '配置巡检'
    assert snapshot.shared_sections[2].title == '高风险配置'
    assert snapshot.shared_sections[3].title == '异常样本'
    assert snapshot.shared_sections[4].title == '配置变更入口'
    assert any('config set site_name RuoYi --output=text' in line for line in snapshot.shared_sections[4].lines)
    assert any(call[0:2] == ('config', 'get') for call in calls)


def test_collect_configs_page_snapshot_sorts_and_filters_risky_records(
    monkeypatch: MonkeyPatch,
    configs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('config', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'databaseCount': 3,
                    'cacheCount': 3,
                    'missingInCacheCount': 1,
                    'orphanInCacheCount': 1,
                    'mismatchCount': 1,
                    'missingInCache': ['upload_mode'],
                    'orphanInCache': ['legacy_toggle'],
                    'mismatchKeys': ['site_name'],
                }
            )
        if arguments[0:2] == ('config', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'configId': 2,
                                'configKey': 'upload_mode',
                                'configName': '上传模式',
                                'configType': 'N',
                                'configValue': 'local',
                            },
                            {
                                'configId': 1,
                                'configKey': 'site_name',
                                'configName': '站点名称',
                                'configType': 'Y',
                                'configValue': 'RuoYi',
                            },
                            {
                                'configId': 3,
                                'configKey': 'normal_timeout',
                                'configName': '会话超时',
                                'configType': 'N',
                                'configValue': '30m',
                            },
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': True, 'key': '-', 'source': 'both', 'inSync': True})

    monkeypatch.setattr(configs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    all_snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev')
    risky_snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev', filter_key='risky')
    mismatch_snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev', filter_key='mismatch')
    cache_drift_snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev', filter_key='cache-drift')

    assert [record.title for record in all_snapshot.records] == [
        'site_name',
        'upload_mode',
        'legacy_toggle',
        'normal_timeout',
    ]
    assert [record.status for record in all_snapshot.records] == ['fail', 'warn', 'warn', 'ok']
    assert any('[值不一致] site_name' in line for line in all_snapshot.shared_sections[2].lines)
    assert any('[缓存缺失] upload_mode' in line for line in all_snapshot.shared_sections[2].lines)
    assert any('[缓存孤立] legacy_toggle' in line for line in all_snapshot.shared_sections[2].lines)

    assert risky_snapshot.active_filter_key == 'risky'
    assert [record.title for record in risky_snapshot.records] == ['site_name', 'upload_mode', 'legacy_toggle']
    assert [record.title for record in mismatch_snapshot.records] == ['site_name']
    assert [record.title for record in cache_drift_snapshot.records] == ['upload_mode', 'legacy_toggle']


def test_collect_configs_page_snapshot_applies_query_filter(
    monkeypatch: MonkeyPatch,
    configs_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('config', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'databaseCount': 2,
                    'cacheCount': 2,
                    'missingInCacheCount': 0,
                    'orphanInCacheCount': 0,
                    'mismatchCount': 0,
                    'missingInCache': [],
                    'orphanInCache': [],
                    'mismatchKeys': [],
                }
            )
        if arguments[0:2] == ('config', 'list'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'page': {
                        'rows': [
                            {
                                'configId': 1,
                                'configKey': 'site_name',
                                'configName': '站点名称',
                                'configType': 'Y',
                                'configValue': 'RuoYi',
                            },
                            {
                                'configId': 2,
                                'configKey': 'upload_mode',
                                'configName': '上传模式',
                                'configType': 'N',
                                'configValue': 'local',
                            },
                        ]
                    },
                }
            )
        return SimpleNamespace(payload={'ok': True, 'key': '-', 'source': 'both', 'inSync': True})

    monkeypatch.setattr(configs_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = configs_adapter.CONFIGS_BROWSER_ADAPTER.collect_snapshot('dev', query='site')

    assert [record.title for record in snapshot.records] == ['site_name']
    assert snapshot.search is not None
    assert snapshot.search.query == 'site'
