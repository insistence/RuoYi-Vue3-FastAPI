from typing import TypeAlias

from pydantic import Field

from plugins.core.validation.dependencies import DependencyCheckResult, DependencyInstallPlanItem
from plugins.core.validation.dependency_policy import DependencyInstallPolicyDecision

from .base import PluginPayloadModel
from .plan import PluginPlanPayloadMixin
from .validation import PluginValidationPayloadMixin


class PluginDependencyInstallPayload(PluginPayloadModel):
    """
    插件依赖安装 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    dependency_ok: bool = Field(alias='dependencyOk')
    dependencies: list[dict[str, object]]
    missing_dependencies: list[str] = Field(alias='missingDependencies')
    unsatisfied_dependencies: list[str] = Field(alias='unsatisfiedDependencies')
    dry_run: bool = Field(alias='dryRun')
    plan: list[dict[str, object]]
    plan_count: int = Field(alias='planCount')
    results: list[dict[str, object]] | None = None
    policy: dict[str, object] | None = None


class DependencyInstallReturnCode(PluginPayloadModel):
    """
    依赖安装命令返回码 payload。
    """

    return_code: int = Field(alias='returnCode')


PluginDependencyInstallPayloadDict: TypeAlias = dict[str, object]
DependencyInstallReturnCodePayload: TypeAlias = dict[str, int]


class PluginDependencyInstallPayloadBuilder:
    """
    插件依赖安装负载构建器。

    使用 Builder 模式统一依赖安装命令的 dry-run、无需安装和执行结果负载。
    """

    @classmethod
    def build_payload(
        cls,
        *,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        dry_run: bool,
        ok: bool,
        message: str,
        results: list[dict[str, object]] | None = None,
        include_results: bool = False,
        policy_decision: DependencyInstallPolicyDecision | None = None,
    ) -> PluginDependencyInstallPayloadDict:
        """
        从依赖检查结果构建依赖安装 payload。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param dry_run: 是否预演
        :param ok: 操作是否成功
        :param message: 操作消息
        :param results: 安装结果列表
        :param include_results: 是否包含安装执行结果
        :param policy_decision: 依赖安装策略判定
        :return: 插件依赖安装 payload
        """
        plan = [PluginPlanPayloadMixin.build_dependency_install_plan_item(item) for item in install_plan_items]
        payload = PluginDependencyInstallPayload(
            ok=ok,
            message=message,
            plugin_id=plugin_id,
            dependency_ok=dependency_result.ok,
            dependencies=[PluginValidationPayloadMixin.build_dependency_item(item) for item in dependency_result.items],
            missing_dependencies=[item.name for item in dependency_result.missing_items],
            unsatisfied_dependencies=[item.name for item in dependency_result.unsatisfied_items],
            dry_run=dry_run,
            plan=plan,
            plan_count=len(plan),
            results=results or [] if include_results else None,
            policy=policy_decision.to_payload() if policy_decision else None,
        )

        return payload.to_payload(exclude_none=True)

    @classmethod
    def build_base_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        *,
        dry_run: bool,
        policy_decision: DependencyInstallPolicyDecision | None = None,
    ) -> PluginDependencyInstallPayloadDict:
        """
        构建插件依赖安装基础负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param dry_run: 是否预演
        :param policy_decision: 依赖安装策略判定
        :return: 插件依赖安装基础负载
        """
        return cls.build_payload(
            plugin_id=plugin_id,
            dependency_result=dependency_result,
            install_plan_items=install_plan_items,
            dry_run=dry_run,
            ok=dependency_result.ok,
            message='插件依赖已满足' if dependency_result.ok else '插件依赖存在问题',
            policy_decision=policy_decision,
        )

    @classmethod
    def build_dry_run_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        policy_decision: DependencyInstallPolicyDecision | None = None,
    ) -> PluginDependencyInstallPayloadDict:
        """
        构建插件依赖安装预演负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param policy_decision: 依赖安装策略判定
        :return: 插件依赖安装预演负载
        """
        return cls.build_payload(
            plugin_id=plugin_id,
            dependency_result=dependency_result,
            install_plan_items=install_plan_items,
            dry_run=True,
            ok=True,
            message='插件依赖安装演练完成，未执行实际安装',
            policy_decision=policy_decision,
        )

    @classmethod
    def build_satisfied_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        policy_decision: DependencyInstallPolicyDecision | None = None,
    ) -> PluginDependencyInstallPayloadDict:
        """
        构建插件依赖已满足负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param policy_decision: 依赖安装策略判定
        :return: 插件依赖已满足负载
        """
        return cls.build_payload(
            plugin_id=plugin_id,
            dependency_result=dependency_result,
            install_plan_items=install_plan_items,
            dry_run=False,
            ok=True,
            message='插件依赖已满足，无需安装',
            include_results=True,
            policy_decision=policy_decision,
        )

    @classmethod
    def build_execution_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        install_plan_items: list[DependencyInstallPlanItem],
        install_results: list[dict[str, object]],
        policy_decision: DependencyInstallPolicyDecision | None = None,
    ) -> PluginDependencyInstallPayloadDict:
        """
        构建插件依赖安装执行结果负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param install_plan_items: 依赖安装计划项列表
        :param install_results: 依赖安装命令执行结果列表
        :param policy_decision: 依赖安装策略判定
        :return: 插件依赖安装执行结果负载
        """
        install_ok = all(result['returnCode'] == 0 for result in install_results)
        return cls.build_payload(
            plugin_id=plugin_id,
            dependency_result=dependency_result,
            install_plan_items=install_plan_items,
            dry_run=False,
            ok=install_ok,
            message='插件依赖安装完成' if install_ok else '插件依赖安装存在失败项',
            results=install_results,
            include_results=True,
            policy_decision=policy_decision,
        )


__all__ = [
    'DependencyInstallReturnCode',
    'DependencyInstallReturnCodePayload',
    'PluginDependencyInstallPayload',
    'PluginDependencyInstallPayloadBuilder',
    'PluginDependencyInstallPayloadDict',
]
