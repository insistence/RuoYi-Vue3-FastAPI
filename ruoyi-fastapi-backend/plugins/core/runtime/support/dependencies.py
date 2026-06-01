import json
from pathlib import Path
from typing import Any

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, SUCCESS
from plugins.core.validation.dependencies import (
    DependencyCheckResult,
    DependencyInstallPlanItem,
    DependencyRequirementParser,
)

from .payload import PluginPayloadBuilder


class PluginDependencyInstallPayloadBuilder:
    """
    插件依赖安装负载构建器。

    使用 Builder 模式统一依赖安装命令的 dry-run、无需安装和执行结果负载。
    """

    @classmethod
    def build_base_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        """
        构建插件依赖安装基础负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param dry_run: 是否预演
        :return: 插件依赖安装基础负载
        """
        plan_items = [PluginPayloadBuilder.build_dependency_install_plan_item(item) for item in install_plan_items]
        return {
            **PluginPayloadBuilder.build_dependency_check_payload(plugin_id, dependency_result),
            'dryRun': dry_run,
            'plan': plan_items,
            'planCount': len(plan_items),
        }

    @classmethod
    def build_dry_run_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
    ) -> dict[str, Any]:
        """
        构建插件依赖安装预演负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :return: 插件依赖安装预演负载
        """
        return {
            **cls.build_base_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                dry_run=True,
            ),
            'ok': True,
            'message': '插件依赖安装演练完成，未执行实际安装',
            'exit_code': SUCCESS,
        }

    @classmethod
    def build_satisfied_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
    ) -> dict[str, Any]:
        """
        构建插件依赖已满足负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :return: 插件依赖已满足负载
        """
        return {
            **cls.build_base_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                dry_run=False,
            ),
            'ok': True,
            'message': '插件依赖已满足，无需安装',
            'results': [],
        }

    @classmethod
    def build_execution_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        install_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        构建插件依赖安装执行结果负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param install_results: 依赖安装命令执行结果列表
        :return: 插件依赖安装执行结果负载
        """
        install_ok = all(result['returnCode'] == 0 for result in install_results)
        return {
            **cls.build_base_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                dry_run=False,
            ),
            'ok': install_ok,
            'message': '插件依赖安装完成' if install_ok else '插件依赖安装存在失败项',
            'results': install_results,
            'exit_code': SUCCESS if install_ok else DEPENDENCY_ERROR,
        }


class PluginNpmPackageJsonSynchronizer:
    """
    插件 npm 依赖声明同步器。

    npm install 可能会把 package.json 写成 npm 自己解析后的版本形式，这里按 plugin.yaml
    中声明的约束回写根 package.json，确保依赖声明与插件 manifest 保持一致。
    """

    @classmethod
    def sync_successful_items(
        cls,
        install_plan_items: list[DependencyInstallPlanItem],
        install_results: list[dict[str, Any]],
    ) -> None:
        """
        同步安装成功的 npm 依赖声明。

        :param install_plan_items: 依赖安装计划项
        :param install_results: 依赖安装执行结果
        :return: None
        """
        for item, result in zip(install_plan_items, install_results, strict=False):
            if item.kind not in {'npm', 'npmDev'} or result['returnCode'] != 0:
                continue
            cls.sync_item(item)

    @staticmethod
    def sync_item(item: DependencyInstallPlanItem) -> None:
        """
        同步单个 npm 依赖版本声明。

        :param item: 依赖安装计划项
        :return: None
        """
        package_json_path = Path(item.workdir) / 'package.json'
        if not package_json_path.is_file():
            return

        package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
        dependency_field = 'devDependencies' if item.kind == 'npmDev' else 'dependencies'
        dependencies = package_json.setdefault(dependency_field, {})
        parsed_dependency = DependencyRequirementParser.parse(item.requirement)
        version = parsed_dependency.required_version
        if version:
            if version.startswith('=='):
                version = version[2:]
            elif version.startswith('='):
                version = version[1:]
            dependencies[parsed_dependency.name] = version
        else:
            dependencies.setdefault(parsed_dependency.name, '*')

        package_json_path.write_text(
            json.dumps(package_json, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
