from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_collect_app_page_snapshot_builds_env_config_and_route_sections(
    monkeypatch: MonkeyPatch,
    app_adapter: ModuleType,
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
                        'appEnv': 'dev',
                        'envFile': '.env.dev',
                        'envFileExists': True,
                        'backendDir': '/srv/backend',
                        'pythonExecutable': '/opt/conda/envs/ruoyi-fastapi/bin/python',
                    },
                }
            )
        if arguments[0:2] == ('app', 'config'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'config': {
                        'name': 'RuoYi',
                        'host': '127.0.0.1',
                        'port': 8000,
                        'rootPath': '/',
                        'workers': 2,
                        'reload': True,
                        'disableSwagger': False,
                        'disableRedoc': True,
                        'logLevel': 'INFO',
                        'dbType': 'mysql',
                        'dbHost': '127.0.0.1',
                        'dbPort': 3306,
                        'dbDatabase': 'ruoyi',
                        'redisHost': '127.0.0.1',
                        'redisPort': 6379,
                        'transportCryptoEnabled': True,
                        'transportCryptoMode': 'strict',
                    },
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
        if arguments[0:2] == ('app', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'env': 'dev',
                    'database': {'ok': True, 'message': '数据库连接成功'},
                    'redis': {'ok': True, 'message': 'Redis连接成功'},
                    'crypto': {'ok': True, 'message': '传输加密配置有效'},
                }
            )
        if arguments[0:2] == ('completion', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': 'completion 诊断信息已生成',
                    'activeShell': 'bash',
                    'projectDir': '/srv/backend',
                    'envChoices': ['dev', 'prod'],
                    'completeEnvVar': '_RUOYI_COMPLETE',
                    'recommendedInstallCommand': 'ruoyi completion install --shell=bash --activate',
                    'shells': {
                        'bash': {
                            'supported': True,
                            'detected': True,
                            'targetFile': '/tmp/ruoyi.bash',
                            'targetFileExists': True,
                            'rcFile': '/Users/demo/.bashrc',
                            'rcFileExists': True,
                            'autoDiscovery': False,
                            'sourceCommand': 'source /tmp/ruoyi.bash',
                            'recommendedInstallCommand': 'ruoyi completion install --shell=bash --activate',
                        },
                        'zsh': {'supported': True, 'detected': False, 'autoDiscovery': False},
                        'fish': {'supported': True, 'detected': False, 'autoDiscovery': True},
                        'powershell': {
                            'supported': True,
                            'detected': False,
                            'autoDiscovery': False,
                            'sourceCommand': '. "/tmp/ruoyi.ps1"',
                            'recommendedInstallCommand': 'ruoyi completion install --shell=powershell --activate',
                        },
                    },
                }
            )
        if arguments[0:2] == ('completion', 'show'):
            return SimpleNamespace(
                returncode=0,
                stdout='_RUOYI_COMPLETE=bash_complete\n_ruoyi_completion() {\n  COMPREPLY=()\n}\n',
                stderr='',
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'count': 3,
                'routes': [
                    {
                        'path': '/system/user/list',
                        'methods': ['GET'],
                        'summary': '查询用户列表',
                    }
                ],
                'groupedRoutes': {
                    'system': [{}, {}],
                    'monitor': [{}],
                },
            }
        )

    monkeypatch.setattr(app_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = app_adapter.APP_DETAIL_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '应用'
    assert (
        snapshot.subtitle
        == '聚焦：环境映射 / 配置摘要 / 启动前检查 | 当前已加载 3 条注册路由，可继续查看环境映射、配置摘要、启动前检查、补全诊断与路由状态'
    )
    assert [section.title for section in snapshot.sections] == [
        '总览判断',
        '环境解析',
        '应用配置',
        '依赖配置',
        '启动前检查',
        '补全诊断',
        '补全脚本预览',
        '补全安装入口',
        '路由摘要',
        '启动入口',
    ]
    assert snapshot.search is not None
    assert snapshot.search.placeholder == '按分区或内容搜索'
    assert any('CLI 环境: dev' in line for line in snapshot.sections[0].lines)
    assert any('CLI 目标环境: dev' in line for line in snapshot.sections[1].lines)
    assert any('监听地址: 127.0.0.1:8000' in line for line in snapshot.sections[2].lines)
    assert any('传输加密: 开启' in line for line in snapshot.sections[3].lines)
    assert any('数据库: 正常' in line for line in snapshot.sections[4].lines)
    assert any('活动 Shell: bash' in line for line in snapshot.sections[5].lines)
    assert any('source /tmp/ruoyi.bash' in line for line in snapshot.sections[5].lines)
    assert any('Shell: bash' in line for line in snapshot.sections[6].lines)
    assert any('_RUOYI_COMPLETE=bash_complete' in line for line in snapshot.sections[6].lines)
    assert any('completion install --activate --output=text' in line for line in snapshot.sections[7].lines)
    assert any('system · 2 条' in line for line in snapshot.sections[8].lines)
    assert any('app run --env=dev' in line for line in snapshot.sections[9].lines)


def test_collect_app_page_snapshot_applies_query_filter(
    monkeypatch: MonkeyPatch,
    app_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('app', 'env'):
            return SimpleNamespace(payload={'ok': True, 'runtime': {'cliEnv': 'dev', 'configEnv': 'dev'}})
        if arguments[0:2] == ('app', 'config'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'config': {
                        'name': 'RuoYi',
                        'host': '127.0.0.1',
                        'port': 8000,
                        'rootPath': '/',
                        'workers': 2,
                        'reload': True,
                        'disableSwagger': False,
                        'disableRedoc': True,
                        'logLevel': 'INFO',
                        'dbType': 'mysql',
                        'dbHost': '127.0.0.1',
                        'dbPort': 3306,
                        'dbDatabase': 'ruoyi',
                        'redisHost': '127.0.0.1',
                        'redisPort': 6379,
                        'transportCryptoEnabled': True,
                        'transportCryptoMode': 'strict',
                    },
                }
            )
        if arguments[0:2] == ('completion', 'doctor'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': 'completion 诊断信息已生成',
                    'activeShell': 'bash',
                    'projectDir': '/srv/backend',
                    'envChoices': ['dev'],
                    'completeEnvVar': '_RUOYI_COMPLETE',
                    'recommendedInstallCommand': 'ruoyi completion install --shell=bash --activate',
                    'shells': {'bash': {'supported': True, 'detected': True, 'autoDiscovery': False}},
                }
            )
        return SimpleNamespace(payload={'ok': True, 'count': 1, 'routes': [], 'groupedRoutes': {}})

    monkeypatch.setattr(app_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = app_adapter.APP_DETAIL_ADAPTER.collect_snapshot('dev', query='路由')

    assert [section.title for section in snapshot.sections] == ['总览判断', '路由摘要']
    assert snapshot.search is not None
    assert snapshot.search.query == '路由'


def test_collect_ops_page_snapshot_builds_health_dependency_and_server_sections(
    monkeypatch: MonkeyPatch,
    ops_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('ops', 'health'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'env': 'dev',
                    'database': {'ok': True, 'message': '数据库连接成功'},
                    'redis': {'ok': True, 'message': 'Redis连接成功'},
                }
            )
        if arguments[0:2] == ('ops', 'ping-db'):
            return SimpleNamespace(payload={'ok': True, 'message': '数据库连接成功'})
        if arguments[0:2] == ('ops', 'ping-redis'):
            return SimpleNamespace(payload={'ok': True, 'message': 'Redis连接成功'})
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
                        'typer': {'installed': True, 'version': '0.12.0'},
                        'alembic': {'installed': True, 'version': '1.13.0'},
                    },
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'server': {
                    'sys': {
                        'computerName': 'ruoyi-node',
                        'computerIp': '10.0.0.8',
                        'osName': 'Linux',
                        'osArch': 'x86_64',
                    },
                    'cpu': {'cpuNum': 8, 'used': 21.5},
                    'mem': {'total': '16 GB', 'usage': 48.2},
                    'py': {'version': '3.10.0', 'runTime': '2天4小时', 'used': '256 MB', 'total': '1 GB'},
                    'sysFiles': [
                        {
                            'dirName': '/',
                            'used': '120 GB',
                            'total': '256 GB',
                            'usage': '46%',
                            'free': '136 GB',
                        }
                    ],
                },
            }
        )

    monkeypatch.setattr(ops_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = ops_adapter.OPS_DETAIL_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '运维'
    assert (
        snapshot.subtitle
        == '聚焦：数据库连通性 / Redis 连通性 / 依赖版本 | 基础探活和依赖状态正常，可继续查看服务器资源与磁盘样本'
    )
    assert [section.title for section in snapshot.sections] == [
        '总览判断',
        '健康检查',
        '数据库探活',
        'Redis 探活',
        '依赖版本',
        '服务器摘要',
        '磁盘样本',
        '生产巡检入口',
    ]
    assert any('探活状态: 正常' in line for line in snapshot.sections[0].lines)
    assert any('数据库: 正常' in line for line in snapshot.sections[1].lines)
    assert any('数据库连接: 正常' in line for line in snapshot.sections[2].lines)
    assert any('Redis 连接: 正常' in line for line in snapshot.sections[3].lines)
    assert any('fastapi · 已安装' in line for line in snapshot.sections[4].lines)
    assert any('主机名: ruoyi-node' in line for line in snapshot.sections[5].lines)
    assert any('使用率 46%' in line for line in snapshot.sections[6].lines)
    assert any('wizard prod-check' in line for line in snapshot.sections[7].lines)
    assert snapshot.search is not None
    assert snapshot.search.placeholder == '按分区或内容搜索'


def test_collect_ops_page_snapshot_surfaces_health_risk_subtitle(
    monkeypatch: MonkeyPatch,
    ops_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('ops', 'health'):
            return SimpleNamespace(
                payload={
                    'ok': False,
                    'env': 'dev',
                    'database': {'ok': False, 'message': '数据库连接失败'},
                    'redis': {'ok': True, 'message': 'Redis连接成功'},
                }
            )
        if arguments[0:2] == ('ops', 'ping-db'):
            return SimpleNamespace(payload={'ok': False, 'message': '数据库连接失败'})
        if arguments[0:2] == ('ops', 'ping-redis'):
            return SimpleNamespace(payload={'ok': True, 'message': 'Redis连接成功'})
        if arguments[0:2] == ('ops', 'deps'):
            return SimpleNamespace(payload={'ok': True, 'missingRequired': [], 'packages': {}, 'message': '依赖正常'})
        return SimpleNamespace(payload={'ok': True, 'server': {'sys': {}, 'cpu': {}, 'mem': {}, 'py': {}}})

    monkeypatch.setattr(ops_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = ops_adapter.OPS_DETAIL_ADAPTER.collect_snapshot('dev')

    assert (
        snapshot.subtitle
        == '聚焦：数据库连通性 / Redis 连通性 / 依赖版本 | 运维探活存在异常，优先核对数据库/Redis 连通性与依赖版本'
    )
