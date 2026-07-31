from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.exit_codes import RUNTIME_ERROR
from cli.utils import format_cli_path


@dataclass(frozen=True)
class PluginScaffoldPlanPayload:
    """
    插件模板写入计划负载。
    """

    template: str
    backend: bool
    frontend: bool
    migration: bool
    seed: bool
    job: bool
    config: bool
    crud: bool
    test: bool
    backend_test: bool
    frontend_test: bool
    frontend_version: str | None
    target_dirs: list[str]
    files: list[tuple[Path, str]]
    conflicts: list[str]

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件模板写入计划负载
        """
        return {
            'backend': self.backend,
            'frontend': self.frontend,
            'template': self.template,
            'migration': self.migration,
            'seed': self.seed,
            'job': self.job,
            'config': self.config,
            'crud': self.crud,
            'test': self.test,
            'backendTest': self.backend_test,
            'frontendTest': self.frontend_test,
            'frontendVersion': self.frontend_version,
            'targetDirs': [format_cli_path(path) for path in self.target_dirs],
            'files': [{'path': path.as_posix(), 'content': content} for path, content in self.files],
            'conflicts': self.conflicts,
        }


@dataclass(frozen=True)
class PluginScaffoldSuccessPayload:
    """
    插件模板创建成功负载。
    """

    plugin_id: str
    scaffold_plan: dict[str, Any]
    dry_run: bool

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件模板创建成功负载
        """
        return {
            'ok': True,
            'message': '插件模板预演完成' if self.dry_run else '插件模板创建成功',
            'pluginId': self.plugin_id,
            'dryRun': self.dry_run,
            **self.scaffold_plan,
        }


@dataclass(frozen=True)
class PluginScaffoldConflictPayload:
    """
    插件模板目录冲突负载。
    """

    plugin_id: str
    scaffold_plan: dict[str, Any]
    dry_run: bool
    failure_code: int = RUNTIME_ERROR

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件模板目录冲突负载
        """
        return {
            'ok': False,
            'message': '插件目录已存在，拒绝覆盖',
            'pluginId': self.plugin_id,
            'dryRun': self.dry_run,
            **self.scaffold_plan,
            'exit_code': self.failure_code,
        }


class PluginScaffoldPayloadBuilder:
    """
    插件模板创建响应负载构建器。
    """

    @staticmethod
    def build_conflict_payload(
        plugin_id: str,
        scaffold_plan: dict[str, Any],
        *,
        dry_run: bool,
        failure_code: int = RUNTIME_ERROR,
    ) -> dict[str, Any]:
        """
        构建插件模板目录冲突负载。

        :param plugin_id: 插件ID
        :param scaffold_plan: 插件模板写入计划
        :param dry_run: 是否预演
        :param failure_code: 失败退出码
        :return: 插件模板目录冲突负载
        """
        return PluginScaffoldConflictPayload(
            plugin_id,
            scaffold_plan,
            dry_run=dry_run,
            failure_code=failure_code,
        ).to_payload()

    @staticmethod
    def build_success_payload(plugin_id: str, scaffold_plan: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        """
        构建插件模板创建成功负载。

        :param plugin_id: 插件ID
        :param scaffold_plan: 插件模板写入计划
        :param dry_run: 是否预演
        :return: 插件模板创建成功负载
        """
        return PluginScaffoldSuccessPayload(plugin_id, scaffold_plan, dry_run=dry_run).to_payload()
