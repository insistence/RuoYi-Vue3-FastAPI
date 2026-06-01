from typing import Any

from cli.exit_codes import RUNTIME_ERROR


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
        return {
            'ok': False,
            'message': '插件目录已存在，拒绝覆盖',
            'pluginId': plugin_id,
            'dryRun': dry_run,
            **scaffold_plan,
            'exit_code': failure_code,
        }

    @staticmethod
    def build_success_payload(plugin_id: str, scaffold_plan: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        """
        构建插件模板创建成功负载。

        :param plugin_id: 插件ID
        :param scaffold_plan: 插件模板写入计划
        :param dry_run: 是否预演
        :return: 插件模板创建成功负载
        """
        return {
            'ok': True,
            'message': '插件模板预演完成' if dry_run else '插件模板创建成功',
            'pluginId': plugin_id,
            'dryRun': dry_run,
            **scaffold_plan,
        }
