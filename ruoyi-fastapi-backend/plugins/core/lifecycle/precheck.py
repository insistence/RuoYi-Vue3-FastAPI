from dataclasses import dataclass

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.validation.result import PluginValidationIssue


@dataclass(frozen=True)
class PluginLifecycleScriptPrecheckResult:
    """
    插件生命周期脚本预检结果。
    """

    issues: list[PluginValidationIssue]

    @property
    def ok(self) -> bool:
        """
        判断生命周期脚本预检是否存在阻断错误。

        :return: 是否不存在 error 级问题
        """
        return not self.error_issues

    @property
    def error_issues(self) -> list[PluginValidationIssue]:
        """
        获取 error 级预检问题。

        :return: error 级问题列表
        """
        return [issue for issue in self.issues if issue.level == 'error']

    @property
    def warning_issues(self) -> list[PluginValidationIssue]:
        """
        获取 warning 级预检问题。

        :return: warning 级问题列表
        """
        return [issue for issue in self.issues if issue.level == 'warning']


class PluginLifecycleScriptPrechecker:
    """
    插件生命周期脚本执行前预检器。
    """

    def __init__(self, discovered_plugin: DiscoveredPlugin, migration_runner: PluginMigrationRunner) -> None:
        """
        初始化生命周期脚本预检器。

        :param discovered_plugin: 已发现插件对象
        :param migration_runner: migration 运行器
        :return: None
        """
        self.discovered_plugin = discovered_plugin
        self.migration_runner = migration_runner

    async def check(self, query_db: object) -> PluginLifecycleScriptPrecheckResult:
        """
        检查 migration 历史和 seed 执行计划。

        :param query_db: orm对象
        :return: 生命周期脚本预检结果
        """
        issues = []
        issues.extend(await self._check_migrations(query_db))
        issues.extend(self._check_seeds())

        return PluginLifecycleScriptPrecheckResult(issues=issues)

    async def _check_migrations(self, query_db: object) -> list[PluginValidationIssue]:
        """
        检查已执行 migration 是否被修改，并输出待执行计划。

        :param query_db: orm对象
        :return: migration 预检问题列表
        """
        issues = []
        migration_paths = PluginMigrationRunner._filter_current_database_migrations(
            self.discovered_plugin.manifest.backend.migrations
        )
        for migration_path in migration_paths:
            migration_file = self.migration_runner._resolve_migration_file(migration_path)
            checksum = PluginMigrationRunner._calculate_checksum(migration_file)
            existing_record = await self.migration_runner._get_existing_record(query_db, migration_path)
            if existing_record and existing_record.status == 'running':
                issues.append(
                    PluginValidationIssue(
                        level='error',
                        category='lifecycle',
                        kind='migration_running',
                        path=f'backend.migrations.{migration_path}',
                        message=f'插件 migration 上次执行仍处于 running 状态：{migration_path}',
                        suggestion='请确认数据库结构状态后手动处理迁移历史',
                    )
                )
                continue
            if existing_record and existing_record.status not in {'success', 'failed'}:
                issues.append(
                    PluginValidationIssue(
                        level='error',
                        category='lifecycle',
                        kind='migration_unknown_status',
                        path=f'backend.migrations.{migration_path}',
                        message=f'插件 migration 历史状态不支持自动执行：{migration_path}，状态：{existing_record.status}',
                        suggestion='请确认数据库结构状态后手动处理迁移历史',
                    )
                )
                continue
            existing_checksum = (
                existing_record.checksum if existing_record and existing_record.status == 'success' else None
            )
            if existing_checksum and existing_checksum != checksum:
                issues.append(
                    PluginValidationIssue(
                        level='error',
                        category='lifecycle',
                        kind='migration_checksum_changed',
                        path=f'backend.migrations.{migration_path}',
                        message=f'插件 migration 已执行但内容已变化：{migration_path}',
                        suggestion='请新增 migration 文件，不要修改已执行的历史 migration',
                    )
                )
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='lifecycle',
                    kind=self._build_migration_status_issue_kind(existing_record),
                    path=f'backend.migrations.{migration_path}',
                    ok=True,
                    message=(
                        f'插件 migration 已执行且校验值一致，将跳过：{migration_path}'
                        if existing_checksum
                        else self._build_migration_pending_message(migration_path, existing_record)
                    ),
                )
            )

        return issues

    @staticmethod
    def _build_migration_status_issue_kind(existing_record: object | None) -> str:
        """
        构建 migration 状态预检问题类型。

        :param existing_record: migration 历史记录
        :return: 预检问题类型
        """
        status = getattr(existing_record, 'status', None)
        if status == 'success':
            return 'migration_already_recorded'
        if status == 'failed':
            return 'migration_failed_retry_pending'
        return 'migration_pending'

    @staticmethod
    def _build_migration_pending_message(migration_path: str, existing_record: object | None) -> str:
        """
        构建 migration 待执行提示。

        :param migration_path: migration 相对路径
        :param existing_record: migration 历史记录
        :return: 待执行提示
        """
        if getattr(existing_record, 'status', None) == 'failed':
            return f'插件 migration 上次执行失败，将在实际操作时重试：{migration_path}'
        return f'插件 migration 将在实际操作时执行：{migration_path}'

    def _check_seeds(self) -> list[PluginValidationIssue]:
        """
        输出 seed 执行计划提示。

        :return: seed 预检问题列表
        """
        seed_paths = PluginSeedRunner._filter_current_database_seeds(self.discovered_plugin.manifest.backend.seeds)

        return [
            PluginValidationIssue(
                level='warning',
                category='lifecycle',
                kind='seed_pending',
                path=f'backend.seeds.{seed_path}',
                ok=True,
                message=f'插件 seed 将在实际操作时执行：{seed_path}',
                suggestion='请确保 seed 脚本可重复执行，避免重复初始化数据',
            )
            for seed_path in seed_paths
        ]
