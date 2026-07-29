import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cli.completion.installers import COMPLETION_INSTALLER, CompletionInstallerService
from cli.core.app_builder import CliApplicationBuilder
from cli.exit_codes import RUNTIME_ERROR
from cli.main import CLI_APPLICATION_BUILDER
from cli.runtime.cache import CACHE_RUNTIME, CacheRuntimeService
from cli.runtime.config import CONFIG_RUNTIME, ConfigRuntimeService
from cli.runtime.crypto import CRYPTO_RUNTIME, CryptoRuntimeService
from cli.runtime.db import DATABASE_RUNTIME, DatabaseRuntimeService
from cli.runtime.gen import GEN_RUNTIME, GenRuntimeService
from cli.runtime.job import JOB_RUNTIME, JobRuntimeService
from cli.runtime.ops import OPERATIONS_RUNTIME, OperationsRuntimeService
from cli.tui.actions.models import TuiActionResult, TuiActionSpec
from cli.tui.copy import TUI_COPY
from cli.utils import SHELL_TEXT_FORMATTER

TUI_ACTION_TIMEOUT_SECONDS = 30.0


@dataclass
class TuiActionExecutionService:
    """
    TUI 动作执行服务。

    该对象将 TUI 动作直接分发到当前进程的 runtime facade，并统一
    施加超时、异常收口和结果文本渲染。动作执行不再启动嵌套 CLI。
    """

    job_runtime: JobRuntimeService = field(default_factory=lambda: JOB_RUNTIME)
    operations_runtime: OperationsRuntimeService = field(default_factory=lambda: OPERATIONS_RUNTIME)
    config_runtime: ConfigRuntimeService = field(default_factory=lambda: CONFIG_RUNTIME)
    cache_runtime: CacheRuntimeService = field(default_factory=lambda: CACHE_RUNTIME)
    gen_runtime: GenRuntimeService = field(default_factory=lambda: GEN_RUNTIME)
    database_runtime: DatabaseRuntimeService = field(default_factory=lambda: DATABASE_RUNTIME)
    crypto_runtime: CryptoRuntimeService = field(default_factory=lambda: CRYPTO_RUNTIME)
    completion_installer: CompletionInstallerService = field(default_factory=lambda: COMPLETION_INSTALLER)
    application_builder: CliApplicationBuilder = field(default_factory=lambda: CLI_APPLICATION_BUILDER)

    async def execute(self, spec: TuiActionSpec, env: str) -> TuiActionResult:
        """
        执行指定 TUI 动作。

        :param spec: 动作定义
        :param env: 当前运行环境
        :return: 动作执行结果
        """
        try:
            payload = await asyncio.wait_for(
                self._dispatch(spec, env),
                timeout=TUI_ACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            payload = {
                'ok': False,
                'message': f'{spec.label}执行超时',
                'error': f'动作未在 {TUI_ACTION_TIMEOUT_SECONDS:g} 秒内完成',
                'exit_code': RUNTIME_ERROR,
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            payload = {
                'ok': False,
                'message': f'{spec.label}执行失败',
                'error': str(exc) or exc.__class__.__name__,
                'exit_code': RUNTIME_ERROR,
            }
        if isinstance(payload, dict):
            payload.setdefault('env', env)
        return TuiActionResult(spec=spec, payload=payload)

    async def _dispatch(self, spec: TuiActionSpec, env: str) -> dict[str, Any]:
        """
        将动作标识分发到对应 runtime。

        :param spec: 动作定义
        :param env: 当前运行环境
        :return: 标准动作结果负载
        """
        action_id = spec.action_id
        parameters = spec.parameters
        if action_id in {'job-run-once', 'job-pause', 'job-resume', 'job-sync'}:
            payload = await self._dispatch_job(action_id, parameters)
        elif action_id == 'config-sync-cache':
            payload = await self.config_runtime.sync_config_cache()
        elif action_id in {'cache-warmup', 'cache-clear-dry-run'}:
            payload = await self._dispatch_cache(action_id, parameters)
        elif action_id in {'gen-export-dry-run', 'gen-sync-db'}:
            payload = await self._dispatch_gen(action_id, parameters)
        elif action_id in {'db-upgrade-dry-run', 'db-init-dry-run'}:
            payload = await self._dispatch_database(action_id, parameters)
        elif action_id in {'ops-ping-db', 'ops-ping-redis'}:
            payload = await self._dispatch_ops(action_id)
        elif action_id == 'app-precheck':
            payload = await self._run_precheck('启动前检查')
        elif action_id == 'prod-check':
            payload = await self._run_precheck('综合运行巡检')
        elif action_id == 'completion-install':
            payload = await self._install_completion()
        elif action_id in {'crypto-keygen', 'crypto-rotate-dry-run'}:
            payload = await self._dispatch_crypto(action_id, parameters)
        else:
            payload = self._unsupported_action(action_id)
        return payload

    async def _dispatch_job(self, action_id: str, parameters: dict[str, object]) -> dict[str, Any]:
        """执行任务领域动作。"""
        job_id = int(parameters.get('job_id') or 0)
        if action_id == 'job-run-once':
            return await self.job_runtime.run_job_once(job_id)
        if action_id == 'job-pause':
            return await self.job_runtime.pause_job(job_id)
        if action_id == 'job-resume':
            return await self.job_runtime.resume_job(job_id)
        if action_id == 'job-sync':
            return await self.operations_runtime.sync_jobs()
        return self._unsupported_action(action_id)

    async def _dispatch_cache(self, action_id: str, parameters: dict[str, object]) -> dict[str, Any]:
        """执行缓存领域动作。"""
        if action_id == 'cache-warmup':
            return await self.cache_runtime.warmup_cache()
        if action_id == 'cache-clear-dry-run':
            return await self.cache_runtime.clear_cache(
                cache_name=str(parameters.get('cache_name') or ''),
                dry_run=True,
            )
        return self._unsupported_action(action_id)

    async def _dispatch_gen(self, action_id: str, parameters: dict[str, object]) -> dict[str, Any]:
        """执行代码生成领域动作。"""
        table_name = str(parameters.get('table_name') or '')
        if action_id == 'gen-export-dry-run':
            return await self.gen_runtime.export_code([table_name], mode='zip', dry_run=True)
        if action_id == 'gen-sync-db':
            return await self.gen_runtime.sync_gen_table_from_db(table_name)
        return self._unsupported_action(action_id)

    async def _dispatch_database(self, action_id: str, parameters: dict[str, object]) -> dict[str, Any]:
        """执行数据库领域动作。"""
        if action_id == 'db-upgrade-dry-run':
            return await asyncio.to_thread(
                self.database_runtime.upgrade_database,
                str(parameters.get('revision') or 'head'),
                dry_run=True,
            )
        if action_id == 'db-init-dry-run':
            return await asyncio.to_thread(self.database_runtime.init_database, dry_run=True)
        return self._unsupported_action(action_id)

    async def _dispatch_ops(self, action_id: str) -> dict[str, Any]:
        """执行运维探活动作。"""
        if action_id == 'ops-ping-db':
            return await self.database_runtime.ping_database()
        if action_id == 'ops-ping-redis':
            return await self.operations_runtime.ping_redis()
        return self._unsupported_action(action_id)

    async def _run_precheck(self, label: str) -> dict[str, Any]:
        """并发执行启动前综合检查。"""
        database, redis, crypto, config = await asyncio.gather(
            self.database_runtime.ping_database(),
            self.operations_runtime.ping_redis(),
            asyncio.to_thread(self.crypto_runtime.validate_crypto_config),
            self.config_runtime.diagnose_config(sample_limit=5),
        )
        checks = (database, redis, crypto, config)
        checks_ok = all(item.get('ok', False) for item in checks)
        return {
            'ok': checks_ok,
            'message': f'{label}通过' if checks_ok else f'{label}发现异常',
            'database': database,
            'redis': redis,
            'crypto': crypto,
            'config': config,
        }

    async def _install_completion(self) -> dict[str, Any]:
        """在当前进程内安装 shell completion。"""
        return await asyncio.to_thread(
            self.completion_installer.install_completion_script,
            self.application_builder.build(),
            None,
            activate=True,
        )

    async def _dispatch_crypto(self, action_id: str, parameters: dict[str, object]) -> dict[str, Any]:
        """执行传输加密领域动作。"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        key_size = int(parameters.get('key_size') or 2048)
        if action_id == 'crypto-keygen':
            return await asyncio.to_thread(
                self.crypto_runtime.generate_crypto_key_pair,
                f'tui-{timestamp}',
                key_size,
            )
        if action_id == 'crypto-rotate-dry-run':
            return await asyncio.to_thread(
                self.crypto_runtime.build_rotation_payload,
                f'tui-next-{timestamp}',
                key_size,
            )
        return self._unsupported_action(action_id)

    @staticmethod
    def _unsupported_action(action_id: str) -> dict[str, Any]:
        """构建未知动作的失败结果，禁止隐式回退到其他操作。"""
        return {
            'ok': False,
            'message': f'不支持的 TUI 动作：{action_id}',
            'exit_code': RUNTIME_ERROR,
        }

    def build_result_lines(self, result: TuiActionResult) -> list[str]:
        """
        构建动作结果详情文本。

        :param result: 动作执行结果
        :return: 结果文本行
        """
        payload = result.payload if isinstance(result.payload, dict) else {}
        lines = [
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('name'),
                result.spec.label,
            ),
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('outcome'),
                TUI_COPY.build_action_result_field_label('success')
                if result.ok
                else TUI_COPY.build_action_result_field_label('fail'),
            ),
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('summary'),
                SHELL_TEXT_FORMATTER.truncate_text(result.message, 88),
            ),
        ]
        service_message = str(payload.get('serviceMessage', '') or '').strip()
        if service_message:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('service'),
                    SHELL_TEXT_FORMATTER.truncate_text(service_message, 88),
                )
            )
        if payload.get('hint'):
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('hint'),
                    SHELL_TEXT_FORMATTER.truncate_text(str(payload.get('hint', '') or ''), 88),
                )
            )
        if payload.get('count') is not None:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('count'),
                    str(payload.get('count')),
                )
            )
        if payload.get('jobId') is not None:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('job_id'),
                    str(payload.get('jobId')),
                )
            )
        operation_label = str(payload.get('operationLabel', '') or '').strip()
        if operation_label and operation_label != result.spec.label:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('operation'),
                    SHELL_TEXT_FORMATTER.truncate_text(operation_label, 64),
                )
            )
        return lines
