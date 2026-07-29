import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import BoundedSemaphore
from typing import Any, TypeVar

from cli.completion.doctor import COMPLETION_DOCTOR, CompletionDoctorService
from cli.completion.installers import COMPLETION_INSTALLER, CompletionInstallerService
from cli.core.app_builder import CliApplicationBuilder
from cli.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR
from cli.main import CLI_APPLICATION_BUILDER
from cli.runtime.app import APP_RUNTIME, AppRuntimeService
from cli.runtime.cache import CACHE_RUNTIME, CacheRuntimeService
from cli.runtime.config import CONFIG_RUNTIME, ConfigRuntimeService
from cli.runtime.crypto import CRYPTO_RUNTIME, CryptoRuntimeService
from cli.runtime.db import DATABASE_RUNTIME, DatabaseRuntimeService
from cli.runtime.gen import GEN_RUNTIME, GenRuntimeService
from cli.runtime.job import JOB_RUNTIME, JobRuntimeService
from cli.runtime.ops import OPERATIONS_RUNTIME, OperationsRuntimeService

TUI_REMOTE_QUERY_TIMEOUT_SECONDS = 3.0
TUI_LOCAL_QUERY_TIMEOUT_SECONDS = 2.0
TUI_PAGE_TIMEOUT_SECONDS = 5.0

_ResultT = TypeVar('_ResultT')


@dataclass(frozen=True)
class TuiGeneratedOutput:
    """
    进程内生成文本结果。

    :param stdout: 生成的标准文本
    :param stderr: 生成失败信息
    :param returncode: 生成结果码
    """

    stdout: str
    stderr: str = ''
    returncode: int = 0


@dataclass(frozen=True)
class TuiQueryExecutor:
    """
    TUI 查询执行器。

    该对象统一施加页面查询超时，并将短时间本地同步检查移出 Textual
    事件循环。网络查询必须通过 ``run_async`` 执行。
    """

    remote_timeout_seconds: float = TUI_REMOTE_QUERY_TIMEOUT_SECONDS
    local_timeout_seconds: float = TUI_LOCAL_QUERY_TIMEOUT_SECONDS
    local_executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=2, thread_name_prefix='ruoyi-tui-query'),
        compare=False,
        repr=False,
    )
    local_slots: BoundedSemaphore = field(
        default_factory=lambda: BoundedSemaphore(2),
        compare=False,
        repr=False,
    )

    async def run_async(
        self,
        operation: Callable[[], Awaitable[_ResultT]],
        *,
        label: str,
    ) -> _ResultT | dict[str, Any]:
        """
        执行带超时的异步查询。

        :param operation: 异步查询工厂
        :param label: 查询名称
        :return: 查询结果或超时负载
        """
        try:
            return await asyncio.wait_for(operation(), timeout=self.remote_timeout_seconds)
        except asyncio.TimeoutError:
            return self.build_timeout_payload(label)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return self.build_failure_payload(label, exc)

    async def run_local(
        self,
        operation: Callable[[], _ResultT],
        *,
        label: str,
    ) -> _ResultT | dict[str, Any]:
        """
        执行带超时的短时间本地同步查询。

        :param operation: 同步查询函数
        :param label: 查询名称
        :return: 查询结果或失败负载
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.local_timeout_seconds
        while not self.local_slots.acquire(blocking=False):
            remaining = deadline - loop.time()
            if remaining <= 0:
                return self.build_timeout_payload(label)
            await asyncio.sleep(min(0.01, remaining))
        try:
            future = loop.run_in_executor(self.local_executor, operation)
        except Exception:
            self.local_slots.release()
            raise
        future.add_done_callback(lambda completed: self.local_slots.release())
        try:
            remaining = max(deadline - loop.time(), 0)
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            return self.build_timeout_payload(label)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return self.build_failure_payload(label, exc)

    @staticmethod
    def build_timeout_payload(label: str) -> dict[str, Any]:
        """
        构建超时结果。

        :param label: 查询名称
        :return: 标准失败负载
        """
        return {
            'ok': False,
            'message': f'{label}超时',
            'error': f'查询未在规定时间内完成：{label}',
            'timeout': True,
            'exit_code': RUNTIME_ERROR,
        }

    @staticmethod
    def build_failure_payload(label: str, exc: Exception) -> dict[str, Any]:
        """
        构建异常结果。

        :param label: 查询名称
        :param exc: 查询异常
        :return: 标准失败负载
        """
        return {
            'ok': False,
            'message': f'{label}失败',
            'error': str(exc) or exc.__class__.__name__,
            'exit_code': RUNTIME_ERROR,
        }


@dataclass
class TuiRuntimeQueryService:
    """
    TUI 进程内查询服务。

    所有 TUI 页面通过该服务直接调用 runtime，不再启动嵌套 CLI 进程。
    """

    app_runtime: AppRuntimeService = field(default_factory=lambda: APP_RUNTIME)
    database_runtime: DatabaseRuntimeService = field(default_factory=lambda: DATABASE_RUNTIME)
    operations_runtime: OperationsRuntimeService = field(default_factory=lambda: OPERATIONS_RUNTIME)
    cache_runtime: CacheRuntimeService = field(default_factory=lambda: CACHE_RUNTIME)
    job_runtime: JobRuntimeService = field(default_factory=lambda: JOB_RUNTIME)
    gen_runtime: GenRuntimeService = field(default_factory=lambda: GEN_RUNTIME)
    config_runtime: ConfigRuntimeService = field(default_factory=lambda: CONFIG_RUNTIME)
    crypto_runtime: CryptoRuntimeService = field(default_factory=lambda: CRYPTO_RUNTIME)
    completion_doctor: CompletionDoctorService = field(default_factory=lambda: COMPLETION_DOCTOR)
    completion_installer: CompletionInstallerService = field(default_factory=lambda: COMPLETION_INSTALLER)
    application_builder: CliApplicationBuilder = field(default_factory=lambda: CLI_APPLICATION_BUILDER)
    executor: TuiQueryExecutor = field(default_factory=TuiQueryExecutor)

    async def get_app_env(self, env: str) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.app_runtime.get_app_env_snapshot,
            label='读取应用环境',
        )
        if isinstance(result, dict) and result.get('ok') is False:
            return result
        if not isinstance(result, dict):
            return self.executor.build_failure_payload(
                '读取应用环境',
                TypeError('应用环境结果格式无效'),
            )
        return {'ok': True, 'env': env, 'runtime': result}

    async def get_app_config(self, env: str) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.app_runtime.get_app_config_snapshot,
            label='读取应用配置',
        )
        if isinstance(result, dict) and result.get('ok') is False:
            return result
        return {'ok': True, 'env': env, 'config': result}

    async def get_app_routes(self, env: str) -> dict[str, Any]:
        result = await self.executor.run_local(
            lambda: self.app_runtime.get_app_routes_snapshot(env, group_by='tag'),
            label='读取应用路由',
        )
        return (
            result
            if isinstance(result, dict)
            else self.executor.build_failure_payload(
                '读取应用路由',
                TypeError('应用路由结果格式无效'),
            )
        )

    async def get_doctor(self, env: str) -> dict[str, Any]:
        database, redis, crypto = await asyncio.gather(
            self.get_database_ping(),
            self.get_redis_ping(),
            self.get_crypto_validation(),
        )
        payload = {
            'env': env,
            'database': database,
            'redis': redis,
            'crypto': crypto,
        }
        payload['ok'] = all(isinstance(item, dict) and item.get('ok', False) for item in (database, redis, crypto))
        if not payload['ok']:
            payload['exit_code'] = DEPENDENCY_ERROR
        return payload

    async def get_completion_doctor(self) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.completion_doctor.build_completion_doctor_payload,
            label='读取补全诊断',
        )
        return (
            result
            if isinstance(result, dict)
            else self.executor.build_failure_payload(
                '读取补全诊断',
                TypeError('补全诊断结果格式无效'),
            )
        )

    async def get_completion_preview(self, shell: str) -> TuiGeneratedOutput:
        def _render() -> str:
            return self.completion_installer.render_completion_script(
                self.application_builder.build(),
                shell,
            )

        result = await self.executor.run_local(_render, label='生成补全脚本')
        if isinstance(result, dict) and not result.get('ok', False):
            return TuiGeneratedOutput(
                stdout='',
                stderr=str(result.get('message') or result.get('error') or '生成补全脚本失败'),
                returncode=1,
            )
        return TuiGeneratedOutput(stdout=str(result))

    async def get_database_ping(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            self.database_runtime.ping_database,
            label='数据库探活',
        )
        return result if isinstance(result, dict) else {}

    async def get_database_current(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            self.database_runtime.get_current_revision_async,
            label='读取数据库版本',
        )
        return result if isinstance(result, dict) else {}

    async def get_database_heads(self) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.database_runtime.get_alembic_heads,
            label='读取 Alembic heads',
        )
        return result if isinstance(result, dict) else {}

    async def get_database_history(self, *, limit: int = 8) -> dict[str, Any]:
        result = await self.executor.run_local(
            lambda: self.database_runtime.get_alembic_history(limit=limit),
            label='读取 Alembic 历史',
        )
        return result if isinstance(result, dict) else {}

    async def get_redis_ping(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            self.operations_runtime.ping_redis,
            label='Redis 探活',
        )
        return result if isinstance(result, dict) else {}

    async def get_dependencies(self) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.operations_runtime.get_dependency_versions,
            label='读取依赖信息',
        )
        return result if isinstance(result, dict) else {}

    async def get_server_info(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            self.operations_runtime.get_server_info,
            label='读取服务器信息',
        )
        return result if isinstance(result, dict) else {}

    async def get_crypto_validation(self) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.crypto_runtime.validate_crypto_config,
            label='校验传输加密配置',
        )
        return result if isinstance(result, dict) else {}

    async def get_crypto_public_key(self) -> dict[str, Any]:
        result = await self.executor.run_local(
            self.crypto_runtime.export_public_key,
            label='读取传输加密公钥',
        )
        return result if isinstance(result, dict) else {}

    async def get_cache_stats(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            self.cache_runtime.get_cache_stats,
            label='读取缓存统计',
        )
        return result if isinstance(result, dict) else {}

    async def get_cache_keys(self, cache_name: str) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.cache_runtime.list_cache_keys(cache_name),
            label='读取缓存键',
        )
        return result if isinstance(result, dict) else {}

    async def get_cache_value(self, cache_name: str, cache_key: str) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.cache_runtime.get_cache_value(cache_name, cache_key),
            label='读取缓存值',
        )
        return result if isinstance(result, dict) else {}

    async def get_cache_ttl(self, cache_name: str, cache_key: str) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.cache_runtime.get_cache_ttl(cache_name, cache_key),
            label='读取缓存 TTL',
        )
        return result if isinstance(result, dict) else {}

    async def get_jobs(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.job_runtime.list_jobs(paged=True, page_size=8),
            label='读取定时任务',
        )
        return result if isinstance(result, dict) else {}

    async def get_job_logs(
        self,
        *,
        job_name: str = '',
        status: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.job_runtime.list_job_logs(
                job_name=job_name,
                status=status,
                paged=True,
                page_size=page_size,
            ),
            label='读取任务日志',
        )
        return result if isinstance(result, dict) else {}

    async def get_job_detail(self, job_id: int) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.job_runtime.get_job_detail(job_id),
            label='读取任务详情',
        )
        return result if isinstance(result, dict) else {}

    async def get_gen_tables(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.gen_runtime.list_gen_tables(paged=True, page_size=8),
            label='读取代码生成业务表',
        )
        return result if isinstance(result, dict) else {}

    async def get_gen_db_tables(self, *, table_name: str = '', page_size: int = 8) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.gen_runtime.list_gen_db_tables(
                table_name=table_name,
                paged=True,
                page_size=page_size,
            ),
            label='读取可导入数据库表',
        )
        return result if isinstance(result, dict) else {}

    async def get_gen_detail(self, table_id: int) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.gen_runtime.get_gen_table_detail(table_id),
            label='读取代码生成详情',
        )
        return result if isinstance(result, dict) else {}

    async def get_gen_preview(self, table_id: int) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.gen_runtime.preview_code(table_id),
            label='生成代码预览',
        )
        return result if isinstance(result, dict) else {}

    async def get_gen_export_dry_run(self, table_name: str) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.gen_runtime.export_code([table_name], mode='zip', dry_run=True),
            label='代码导出演练',
        )
        return result if isinstance(result, dict) else {}

    async def get_configs(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.config_runtime.list_configs(paged=True, page_size=8),
            label='读取参数配置',
        )
        return result if isinstance(result, dict) else {}

    async def get_config_diagnostics(self) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.config_runtime.diagnose_config(sample_limit=5),
            label='诊断参数配置',
        )
        return result if isinstance(result, dict) else {}

    async def get_config_detail(self, config_key: str) -> dict[str, Any]:
        result = await self.executor.run_async(
            lambda: self.config_runtime.get_config(config_key, source='both'),
            label='读取参数配置详情',
        )
        return result if isinstance(result, dict) else {}


TUI_RUNTIME_QUERIES = TuiRuntimeQueryService()
