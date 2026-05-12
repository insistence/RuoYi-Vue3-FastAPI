import importlib
import os
import sys
from pathlib import Path

from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.completion.providers', None)
sys.modules.pop('cli', None)

completion_support = importlib.import_module('cli.completion.providers')
completion_gateway = completion_support.COMPLETION_PROVIDER_GATEWAY
completion_registry = completion_gateway.provider_registry


def test_complete_alembic_revisions_returns_default_choices_and_local_revisions(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    校验 Alembic 版本补全会返回默认候选和本地迁移版本。

    :param tmp_path: pytest 临时目录
    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    versions_dir = tmp_path / 'alembic' / 'versions'
    versions_dir.mkdir(parents=True)
    (versions_dir / '2026_04_29_1000-abc123_add_demo_table.py').write_text('# test', encoding='utf-8')

    monkeypatch.chdir(tmp_path)

    candidates = completion_gateway.complete_alembic_revisions(None, None, 'a')
    default_candidates = completion_gateway.complete_alembic_revisions(None, None, '')

    assert 'abc123' in candidates
    assert 'head' in default_candidates
    assert 'base' in default_candidates
    assert 'current' in default_candidates
    assert '-1' in default_candidates


def test_complete_sql_files_returns_project_relative_sql_paths(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    校验 SQL 文件补全会返回项目相对路径。

    :param tmp_path: pytest 临时目录
    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    sql_dir = tmp_path / 'sql'
    sql_dir.mkdir()
    (sql_dir / 'demo.sql').write_text('select 1;', encoding='utf-8')

    monkeypatch.chdir(tmp_path)

    candidates = completion_gateway.complete_sql_files(None, None, 'sql/d')

    assert candidates == ['sql/demo.sql']


def test_complete_cache_names_returns_static_cache_name_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验缓存名称补全会返回系统内置缓存名称。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeCacheKeyConfig:
        """
        模拟缓存键配置对象。
        """

        def __init__(self, key: str) -> None:
            """
            初始化模拟缓存键配置对象。

            :param key: 缓存名称
            :return: None
            """
            self.key = key

    class _FakeEnumsModule:
        """
        模拟枚举模块。
        """

        RedisInitKeyConfig = [_FakeCacheKeyConfig('sys_config'), _FakeCacheKeyConfig('login_tokens')]

    monkeypatch.setattr(
        completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeEnumsModule
    )

    candidates = completion_gateway.complete_cache_names(None, None, 'sys')

    assert candidates == ['sys_config']


def test_complete_output_paths_returns_directories_and_zip_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """
    校验导出路径补全会返回目录和 zip 文件。

    :param tmp_path: pytest 临时目录
    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    build_dir = tmp_path / 'build'
    build_dir.mkdir()
    (build_dir / 'gen.zip').write_text('zip', encoding='utf-8')
    (build_dir / 'notes.txt').write_text('ignore', encoding='utf-8')

    monkeypatch.chdir(tmp_path)

    candidates = completion_gateway.complete_output_paths(None, None, 'build/')

    assert 'build/gen.zip' in candidates
    assert 'build/notes.txt' not in candidates


def test_complete_config_keys_returns_dynamic_readonly_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验参数键名补全会返回动态只读查询结果。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeConfigRuntime:
        """
        模拟配置运行时模块。
        """

        class ConfigRuntime:
            """
            模拟配置运行时服务对象。
            """

            @staticmethod
            def list_configs(**kwargs: str) -> dict:
                """
                模拟配置列表查询入口。

                :param kwargs: 查询参数
                :return: 伪造的结果字典
                """
                return kwargs

        CONFIG_RUNTIME = ConfigRuntime()

    monkeypatch.setattr(
        completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeConfigRuntime
    )
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'run_completion_coroutine',
        lambda coroutine, *, env: {
            'ok': True,
            'items': [
                {'configKey': 'sys.user.initPassword'},
                {'configKey': 'sys.user.maxRetryCount'},
            ],
        },
    )

    candidates = completion_gateway.complete_config_keys(None, None, 'sys.user.i')

    assert candidates == ['sys.user.initPassword']


def test_complete_gen_table_names_returns_dynamic_readonly_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验代码生成业务表补全会返回动态只读查询结果。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeGenRuntime:
        """
        模拟代码生成运行时模块。
        """

        class GenRuntime:
            """
            模拟代码生成运行时服务对象。
            """

            @staticmethod
            def list_gen_tables(**kwargs: str) -> dict:
                """
                模拟业务表列表查询入口。

                :param kwargs: 查询参数
                :return: 伪造的结果字典
                """
                return kwargs

            @staticmethod
            def list_gen_db_tables(**kwargs: str) -> dict:
                """
                模拟数据库物理表列表查询入口。

                :param kwargs: 查询参数
                :return: 伪造的结果字典
                """
                return kwargs

        GEN_RUNTIME = GenRuntime()

    monkeypatch.setattr(completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeGenRuntime)
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'run_completion_coroutine',
        lambda coroutine, *, env: {
            'ok': True,
            'items': [
                {'tableName': 'sys_user'},
                {'tableName': 'sys_role'},
            ],
        },
    )

    candidates = completion_gateway.complete_gen_table_names(None, None, 'sys_u')

    assert candidates == ['sys_user']


def test_dynamic_completion_returns_empty_list_when_runtime_fails(monkeypatch: MonkeyPatch) -> None:
    """
    校验动态补全在运行时失败时会优雅降级为空列表。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'load_runtime_module',
        lambda module_name: (_ for _ in ()).throw(RuntimeError('boom')),
    )

    candidates = completion_gateway.complete_gen_db_table_names(None, None, 'sys')

    assert candidates == []


def test_complete_cache_keys_returns_dynamic_readonly_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验缓存键名补全会基于缓存名称返回动态只读查询结果。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeCacheRuntime:
        """
        模拟缓存运行时模块。
        """

        class CacheRuntime:
            """
            模拟缓存运行时服务对象。
            """

            @staticmethod
            def list_cache_keys(cache_name: str) -> dict[str, str]:
                """
                模拟缓存键列表查询入口。

                :param cache_name: 缓存名称
                :return: 伪造的参数字典
                """
                return {'cache_name': cache_name}

        CACHE_RUNTIME = CacheRuntime()

    class _FakeContext:
        """
        模拟 Click 上下文。
        """

        params = {'cache_name': 'sys_config'}

    monkeypatch.setattr(
        completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeCacheRuntime
    )
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'run_completion_coroutine',
        lambda coroutine, *, env: {
            'ok': True,
            'keys': ['site.name', 'site.logo'],
        },
    )

    candidates = completion_gateway.complete_cache_keys(_FakeContext(), None, 'site.n')

    assert candidates == ['site.name']


def test_complete_job_names_returns_dynamic_readonly_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验任务名称补全会返回动态只读查询结果。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeJobRuntime:
        """
        模拟任务运行时模块。
        """

        class JobRuntime:
            """
            模拟任务运行时服务对象。
            """

            @staticmethod
            def list_jobs(**kwargs: str) -> dict:
                """
                模拟任务列表查询入口。

                :param kwargs: 查询参数
                :return: 伪造的参数字典
                """
                return kwargs

        JOB_RUNTIME = JobRuntime()

    monkeypatch.setattr(completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeJobRuntime)
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'run_completion_coroutine',
        lambda coroutine, *, env: {
            'ok': True,
            'items': [
                {'jobName': '同步任务'},
                {'jobName': '缓存预热'},
            ],
        },
    )

    candidates = completion_gateway.complete_job_names(None, None, '同')

    assert candidates == ['同步任务']


def test_complete_job_ids_returns_dynamic_readonly_choices(monkeypatch: MonkeyPatch) -> None:
    """
    校验任务 ID 补全会返回动态只读查询结果。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class _FakeJobRuntime:
        """
        模拟任务运行时模块。
        """

        class JobRuntime:
            """
            模拟任务运行时服务对象。
            """

            @staticmethod
            def list_jobs(**kwargs: str) -> dict:
                """
                模拟任务列表查询入口。

                :param kwargs: 查询参数
                :return: 伪造的参数字典
                """
                return kwargs

        JOB_RUNTIME = JobRuntime()

    monkeypatch.setattr(completion_registry.dynamic_service, 'load_runtime_module', lambda module_name: _FakeJobRuntime)
    monkeypatch.setattr(
        completion_registry.dynamic_service,
        'run_completion_coroutine',
        lambda coroutine, *, env: {
            'ok': True,
            'items': [
                {'jobId': 101},
                {'jobId': 202},
            ],
        },
    )

    candidates = completion_gateway.complete_job_ids(None, None, '1')

    assert candidates == ['101']


def test_run_completion_coroutine_scopes_app_env(monkeypatch: MonkeyPatch) -> None:
    """
    校验动态补全执行时会临时注入 APP_ENV，并在结束后恢复原值。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    monkeypatch.setenv('APP_ENV', 'prod')
    captured: dict[str, str | None] = {}

    async def _read_env() -> str | None:
        captured['during'] = os.environ.get('APP_ENV')
        return captured['during']

    result = completion_registry.dynamic_service.run_completion_coroutine(_read_env(), env='dev')

    assert result == 'dev'
    assert captured['during'] == 'dev'
    assert os.environ.get('APP_ENV') == 'prod'


def test_run_completion_coroutine_clears_scoped_app_env_when_original_missing(monkeypatch: MonkeyPatch) -> None:
    """
    校验动态补全执行结束后会移除临时注入的 APP_ENV。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    monkeypatch.delenv('APP_ENV', raising=False)

    async def _read_env() -> str | None:
        return os.environ.get('APP_ENV')

    result = completion_registry.dynamic_service.run_completion_coroutine(_read_env(), env='dockerpg')

    assert result == 'dockerpg'
    assert 'APP_ENV' not in os.environ
