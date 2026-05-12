from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_collect_cache_page_snapshot_builds_cache_browser_records(
    monkeypatch: MonkeyPatch,
    cache_adapter: ModuleType,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        calls.append(arguments)
        if arguments[0:2] == ('cache', 'stats'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'dbSize': 128,
                    'info': {
                        'redis_version': '7.0',
                        'connected_clients': 12,
                        'used_memory_human': '16M',
                    },
                    'commandStats': [{'name': 'get', 'value': 88}],
                    'cacheNames': [{'cacheName': 'sys_config', 'remark': '系统参数缓存'}],
                }
            )
        if arguments[0:2] == ('cache', 'keys'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'cacheName': 'sys_config',
                    'count': 2,
                    'keys': ['site_name', 'site_logo'],
                }
            )
        if arguments[0:2] == ('cache', 'get'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'cacheName': 'sys_config',
                    'cacheKey': arguments[3],
                    'cacheValue': 'hello-world',
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'cacheName': 'sys_config',
                'cacheKey': arguments[3],
                'ttlSeconds': 3600,
                'persistent': False,
                'expires': True,
            }
        )

    monkeypatch.setattr(cache_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = cache_adapter.CACHE_BROWSER_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '缓存'
    assert (
        snapshot.subtitle
        == '聚焦：Redis 键数 / 连接数 / 缓存名前缀 | 缓存基线正常，当前已加载 1 个缓存名，Redis 键数 128，连接数 12，可继续查看键列表、键值样本和 TTL'
    )
    assert len(snapshot.records) == 1
    assert snapshot.records[0].title == 'sys_config'
    detail_sections = snapshot.records[0].resolve_detail_sections()
    assert [section.title for section in detail_sections] == [
        '键摘要',
        '键列表',
        '键详情 · site_name',
        '键详情 · site_logo',
    ]
    assert any('site_name' in line for line in detail_sections[1].lines)
    assert any('TTL: 3600 秒' in line for line in detail_sections[2].lines)
    assert any('hello-world' in line for line in detail_sections[2].lines)
    assert any('TTL: 3600 秒' in line for line in detail_sections[3].lines)
    assert snapshot.shared_sections[0].title == '总览判断'
    assert any('已登记缓存名: 1 个' in line for line in snapshot.shared_sections[0].lines)
    assert any('当前匹配: 1 个' in line for line in snapshot.shared_sections[0].lines)
    assert snapshot.shared_sections[1].title == 'Redis 摘要'
    assert snapshot.shared_sections[2].title == '命令统计'
    assert snapshot.shared_sections[3].title == '缓存清理入口'
    assert any('wizard cache-clear' in line for line in snapshot.shared_sections[3].lines)
    assert any(call[0:2] == ('cache', 'get') for call in calls)
    assert any(call[0:2] == ('cache', 'ttl') for call in calls)


def test_cache_browser_adapter_collect_snapshot_exposes_search_context(
    monkeypatch: MonkeyPatch,
    cache_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('cache', 'stats'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'dbSize': 8,
                    'info': {
                        'redis_version': '7.0',
                        'connected_clients': 2,
                        'used_memory_human': '1M',
                    },
                    'commandStats': [],
                    'cacheNames': [{'cacheName': 'sys_config', 'remark': '系统参数缓存'}],
                }
            )
        return SimpleNamespace(payload={'ok': False, 'message': 'unexpected'})

    monkeypatch.setattr(cache_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = cache_adapter.CACHE_BROWSER_ADAPTER.collect_snapshot('dev', query='sys')

    assert snapshot.title == '缓存'
    assert snapshot.search is not None
    assert snapshot.search.query == 'sys'
    assert snapshot.records
    assert snapshot.records[0].title == 'sys_config'


def test_collect_database_page_snapshot_builds_check_heads_and_history_sections(
    monkeypatch: MonkeyPatch,
    database_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(payload={'ok': True, 'currentRevision': '202604300001'})
        if arguments[0:2] == ('db', 'check'):
            return SimpleNamespace(payload={'ok': True, 'message': '数据库连接成功'})
        if arguments[0:2] == ('db', 'heads'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': '已读取 Alembic heads',
                    'count': 1,
                    'items': [
                        {
                            'revision': '202604300001',
                            'downRevisions': ['202604290001'],
                            'branchLabels': ['main'],
                            'dependsOn': [],
                            'doc': 'create user table',
                            'path': '/srv/backend/alembic/versions/202604300001_create_user.py',
                        }
                    ],
                }
            )
        if arguments[0:2] == ('db', 'history'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': '已读取 Alembic 历史版本',
                    'count': 2,
                    'totalCount': 2,
                    'limit': 8,
                    'items': [
                        {
                            'revision': '202604300001',
                            'downRevisions': ['202604290001'],
                            'branchLabels': ['main'],
                            'dependsOn': [],
                            'doc': 'create user table',
                            'path': '/srv/backend/alembic/versions/202604300001_create_user.py',
                        },
                        {
                            'revision': '202604290001',
                            'downRevisions': [],
                            'branchLabels': [],
                            'dependsOn': [],
                            'doc': 'init schema',
                            'path': '/srv/backend/alembic/versions/202604290001_init_schema.py',
                        },
                    ],
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'config': {
                    'dbType': 'mysql',
                    'dbHost': '127.0.0.1',
                    'dbPort': 3306,
                    'dbDatabase': 'ruoyi',
                },
            }
        )

    monkeypatch.setattr(database_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = database_adapter.DATABASE_DETAIL_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '数据库'
    assert (
        snapshot.subtitle
        == '聚焦：迁移版本 / 连接状态 / Heads | 数据库基线正常，当前 revision 202604300001，可继续查看连接、heads 和历史版本'
    )
    assert [section.title for section in snapshot.sections] == [
        '总览判断',
        '迁移版本',
        '连接信息',
        '连通性检查',
        'Heads 状态',
        '历史版本',
        '初始化预演入口',
        '升级入口',
    ]
    assert any('当前 revision: 202604300001' in line for line in snapshot.sections[0].lines)
    assert any('迁移版本: 202604300001' in line for line in snapshot.sections[1].lines)
    assert any('连接地址: 127.0.0.1:3306' in line for line in snapshot.sections[2].lines)
    assert any('数据库连接: 正常' in line for line in snapshot.sections[3].lines)
    assert any('Heads 数量: 1' in line for line in snapshot.sections[4].lines)
    assert any('Head 01 · 202604300001' in line for line in snapshot.sections[4].lines)
    assert any('总版本数: 2' in line for line in snapshot.sections[5].lines)
    assert any('版本 02 · 202604290001' in line for line in snapshot.sections[5].lines)
    assert any('db init --dry-run --output=text' in line for line in snapshot.sections[6].lines)
    assert any('wizard db-upgrade' in line for line in snapshot.sections[7].lines)
    assert snapshot.search is not None
    assert snapshot.search.placeholder == '按 revision 搜索'


def test_collect_database_page_snapshot_surfaces_failed_heads(
    monkeypatch: MonkeyPatch,
    database_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(payload={'ok': True, 'currentRevision': '202604300001'})
        if arguments[0:2] == ('db', 'check'):
            return SimpleNamespace(payload={'ok': True, 'message': '数据库连接成功'})
        if arguments[0:2] == ('db', 'heads'):
            return SimpleNamespace(payload={'ok': False, 'message': '读取 Alembic heads 失败', 'error': 'broken graph'})
        if arguments[0:2] == ('db', 'history'):
            return SimpleNamespace(payload={'ok': True, 'count': 0, 'totalCount': 0, 'limit': 8, 'items': []})
        return SimpleNamespace(
            payload={
                'ok': True,
                'config': {
                    'dbType': 'mysql',
                    'dbHost': '127.0.0.1',
                    'dbPort': 3306,
                    'dbDatabase': 'ruoyi',
                },
            }
        )

    monkeypatch.setattr(database_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = database_adapter.DATABASE_DETAIL_ADAPTER.collect_snapshot('dev')

    assert snapshot.subtitle == '聚焦：迁移版本 / 连接状态 / Heads | 数据库存在迁移分叉风险，优先确认 heads 和历史版本'
    assert snapshot.sections[0].title == '总览判断'
    assert snapshot.sections[0].status == 'warn'
    assert snapshot.sections[4].title == 'Heads 状态'
    assert snapshot.sections[4].status == 'fail'
    assert any('读取 Alembic heads 失败' in line for line in snapshot.sections[4].lines)


def test_collect_database_page_snapshot_applies_query_filter(
    monkeypatch: MonkeyPatch,
    database_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('db', 'current'):
            return SimpleNamespace(payload={'ok': True, 'currentRevision': '202604300001'})
        if arguments[0:2] == ('db', 'check'):
            return SimpleNamespace(payload={'ok': True, 'message': '数据库连接成功'})
        if arguments[0:2] == ('db', 'heads'):
            return SimpleNamespace(payload={'ok': True, 'count': 1, 'items': []})
        if arguments[0:2] == ('db', 'history'):
            return SimpleNamespace(payload={'ok': True, 'count': 0, 'totalCount': 0, 'limit': 8, 'items': []})
        return SimpleNamespace(
            payload={
                'ok': True,
                'config': {'dbType': 'mysql', 'dbHost': '127.0.0.1', 'dbPort': 3306, 'dbDatabase': 'ruoyi'},
            }
        )

    monkeypatch.setattr(database_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = database_adapter.DATABASE_DETAIL_ADAPTER.collect_snapshot('dev', query='历史')

    assert [section.title for section in snapshot.sections] == ['历史版本']
    assert snapshot.search is not None
    assert snapshot.search.query == '历史'


def test_collect_crypto_page_snapshot_builds_validate_and_public_key_sections(
    monkeypatch: MonkeyPatch,
    crypto_adapter: ModuleType,
) -> None:
    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('crypto', 'validate'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'message': '传输加密配置校验通过',
                }
            )
        return SimpleNamespace(
            payload={
                'ok': True,
                'publicKey': {
                    'kid': 'default',
                    'alg': 'RSA-OAEP',
                    'envelopeVersion': 'v1',
                    'expireAt': '2099-12-31T23:59:59',
                    'supportedKids': ['default', 'legacy-a'],
                    'publicKey': '-----BEGIN PUBLIC KEY-----\nAAA\nBBB\n-----END PUBLIC KEY-----',
                },
            }
        )

    monkeypatch.setattr(crypto_adapter.NESTED_CLI_SUPPORT, 'run', fake_run_nested_cli_command)

    snapshot = crypto_adapter.CRYPTO_DETAIL_ADAPTER.collect_snapshot('dev')

    assert snapshot.title == '传输加密'
    assert (
        snapshot.subtitle
        == '聚焦：运行校验 / 公钥身份 / 兼容版本 | 当前 KID default，兼容版本 2 个，可继续查看公钥身份、兼容版本与轮换预演入口'
    )
    assert [section.title for section in snapshot.sections] == [
        '总览判断',
        '运行校验',
        '公钥身份',
        '兼容版本',
        '公钥预览',
        '密钥生成入口',
        '轮换预演入口',
    ]
    assert any('运行校验: 通过' in line for line in snapshot.sections[0].lines)
    assert any('状态: 通过' in line for line in snapshot.sections[1].lines)
    assert any('KID: default' in line for line in snapshot.sections[2].lines)
    assert any('支持版本: legacy-a' in line for line in snapshot.sections[3].lines)
    assert any('BEGIN PUBLIC KEY' in line for line in snapshot.sections[4].lines)
    assert any('crypto keygen' in line for line in snapshot.sections[5].lines)
    assert any('crypto rotate' in line for line in snapshot.sections[6].lines)
    assert snapshot.search is not None
    assert snapshot.search.placeholder == '按分区或内容搜索'
