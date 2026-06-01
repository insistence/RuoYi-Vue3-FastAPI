from typing import Any

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, SUCCESS

from .payload import PluginPayloadBuilder
from .precheck import PluginPrecheckContext


class PluginLifecyclePayloadBuilder:
    """
    插件安装与升级生命周期负载构建器。

    使用 Builder 模式集中安装、升级流程中的 dry-run、阻断和成功结果负载。
    """

    @staticmethod
    def build_install_dry_run_payload(
        plugin_id: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
    ) -> dict[str, Any]:
        """
        构建插件安装预演负载。

        :param plugin_id: 插件ID
        :param actions: 安装动作清单
        :param precheck: 插件操作预检上下文
        :return: 插件安装预演负载
        """
        return {
            'ok': True,
            'message': '插件安装演练完成，未执行实际写入',
            'pluginId': plugin_id,
            'dryRun': True,
            'actions': actions,
            **precheck.operation_payload,
        }

    @staticmethod
    def build_precheck_blocker_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        dry_run: bool = False,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        构建插件安装或升级预检阻断负载。

        :param plugin_id: 插件ID
        :param message: 阻断提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param dry_run: 是否预演
        :param extra_payload: 额外负载
        :return: 插件安装或升级预检阻断负载
        """
        return {
            'ok': False,
            'message': message,
            'pluginId': plugin_id,
            'dryRun': dry_run,
            **(extra_payload or {}),
            'actions': actions,
            **precheck.operation_payload,
            'exit_code': DEPENDENCY_ERROR,
        }

    @classmethod
    def build_first_precheck_blocker_payload(
        cls,
        plugin_id: str,
        *,
        operation: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        按统一优先级构建首个预检阻断负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param extra_payload: 额外负载
        :return: 预检阻断负载，无需阻断时返回 None
        """
        operation_label = {
            'install': '安装',
            'enable': '启用',
            'upgrade': '升级',
            'uninstall': '卸载',
            'purge': '物理清理',
        }.get(operation, '操作')
        blocker_specs = [
            (precheck.manifest_result.ok, 'manifestOk', f'插件 manifest 检查失败，{operation_label}已中止'),
            (
                precheck.plugin_dependency_result.ok,
                'pluginDependencyOk',
                f'插件间依赖检查失败，{operation_label}已中止',
            ),
            (precheck.structure_result.ok, 'structureOk', f'插件结构检查失败，{operation_label}已中止'),
            (precheck.menu_conflict_result.ok, 'menuConflictOk', f'插件菜单存在冲突，{operation_label}已中止'),
        ]
        for ok, payload_key, message in blocker_specs:
            if ok:
                continue
            return cls.build_precheck_blocker_payload(
                plugin_id,
                message=message,
                actions=actions,
                precheck=precheck,
                extra_payload={**(extra_payload or {}), payload_key: False},
            )

        return None

    @classmethod
    def build_dependency_blocker_payload(
        cls,
        plugin_id: str,
        *,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        dependency_install_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        构建依赖自动安装后仍未满足时的阻断负载。

        :param plugin_id: 插件ID
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param dependency_install_payload: 依赖安装执行负载
        :return: 依赖阻断负载，无需阻断时返回 None
        """
        if precheck.dependency_result.ok:
            return None

        return cls.build_precheck_blocker_payload(
            plugin_id,
            message='插件依赖检查失败，安装已中止',
            actions=actions,
            precheck=precheck,
            extra_payload={'dependencyOk': False, 'dependencyInstall': dependency_install_payload},
        )

    @staticmethod
    def build_operation_dry_run_payload(
        plugin_id: str,
        *,
        operation: str,
        message: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        extra_payload: dict[str, Any] | None = None,
        ok_from_precheck: bool = True,
    ) -> dict[str, Any]:
        """
        构建统一预检后的操作预演负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param message: 预演提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param extra_payload: 额外负载
        :param ok_from_precheck: 是否使用预检结果决定操作是否成功
        :return: 操作预演负载
        """
        ok = precheck.ok if ok_from_precheck else True
        return {
            'ok': ok,
            'message': message if ok else '插件操作预检存在问题，未执行实际写入',
            'pluginId': plugin_id,
            'operation': operation,
            'dryRun': True,
            **(extra_payload or {}),
            'actions': actions,
            **precheck.operation_payload,
            'precheck': precheck.check_payload,
            'exit_code': SUCCESS if ok else DEPENDENCY_ERROR,
        }

    @staticmethod
    def build_installed_menu_conflict_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        installed_menu_conflicts: list[Any],
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        构建已安装菜单冲突阻断负载。

        :param plugin_id: 插件ID
        :param message: 阻断提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param installed_menu_conflicts: 已安装菜单冲突列表
        :param extra_payload: 额外负载
        :return: 已安装菜单冲突阻断负载
        """
        menu_conflicts = [
            *precheck.menu_conflicts,
            *[PluginPayloadBuilder.build_menu_conflict_item(item) for item in installed_menu_conflicts],
        ]
        return {
            'ok': False,
            'message': message,
            'pluginId': plugin_id,
            'dryRun': False,
            **(extra_payload or {}),
            'actions': actions,
            **precheck.operation_payload,
            'menuConflicts': menu_conflicts,
            'menuConflictOk': False,
            'exit_code': DEPENDENCY_ERROR,
        }

    @staticmethod
    def build_upgrade_latest_payload(
        plugin_id: str,
        version_state: dict[str, Any],
        precheck: PluginPrecheckContext,
    ) -> dict[str, Any]:
        """
        构建插件无需升级负载。

        :param plugin_id: 插件ID
        :param version_state: 插件升级版本状态
        :param precheck: 插件操作预检上下文
        :return: 插件无需升级负载
        """
        return {
            'ok': True,
            'message': '插件已是最新版本，无需升级',
            'pluginId': plugin_id,
            'dryRun': False,
            **version_state,
            'actions': [],
            **precheck.operation_payload,
        }

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
        plugin: Any,
        installed_configs: list[Any],
        migration_results: list[Any],
        seed_results: list[Any],
        hook_result: Any | None,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        构建插件安装或升级成功负载。

        :param plugin_id: 插件ID
        :param message: 成功提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param plugin: 插件数据库模型
        :param installed_configs: 已安装配置列表
        :param migration_results: migration 执行结果列表
        :param seed_results: seed 执行结果列表
        :param hook_result: 生命周期钩子执行结果
        :param extra_payload: 额外负载
        :return: 插件安装或升级成功负载
        """
        return {
            'ok': True,
            'message': message,
            'pluginId': plugin_id,
            'dryRun': False,
            **(extra_payload or {}),
            'actions': actions,
            **precheck.operation_payload,
            'plugin': plugin.model_dump(by_alias=True),
            'configs': [config.model_dump(by_alias=True) for config in installed_configs],
            'migrations': [migration_result.__dict__ for migration_result in migration_results],
            'seeds': [seed_result.__dict__ for seed_result in seed_results],
            'hooks': [hook_result.__dict__] if hook_result else [],
        }
