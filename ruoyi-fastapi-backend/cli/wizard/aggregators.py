from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProdCheckPayloadSupport:
    """
    `wizard prod-check` 结果提取支持对象。

    该对象负责从多路只读结果中提取 runtime、doctor、config
    片段，避免聚合器本体继续堆叠细碎字段判定逻辑。
    """

    @staticmethod
    def extract_runtime_payload(runtime_payload: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        提取运行环境结果中的 runtime 片段。

        :param runtime_payload: 运行环境结果
        :return: runtime 片段
        """
        return runtime_payload.get('runtime') if isinstance(runtime_payload, dict) else None

    @staticmethod
    def extract_doctor_payload(doctor_payload: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        提取应用检查结果片段。

        :param doctor_payload: 应用检查结果
        :return: doctor 片段
        """
        return doctor_payload if isinstance(doctor_payload, dict) else None

    @staticmethod
    def extract_config_payload(config_payload: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        提取配置快照结果中的 config 片段。

        :param config_payload: 配置快照结果
        :return: config 片段
        """
        return config_payload.get('config') if isinstance(config_payload, dict) else None


@dataclass(frozen=True)
class ProdCheckStatusEvaluator:
    """
    `wizard prod-check` 状态评估器。

    该对象负责统一计算聚合结果的成功状态和标准消息。
    """

    @staticmethod
    def is_ok(
        runtime_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
    ) -> bool:
        """
        计算生产巡检聚合结果是否成功。

        :param runtime_payload: 运行环境结果
        :param doctor_payload: 应用检查结果
        :param config_payload: 配置快照结果
        :return: 是否成功
        """
        return (
            bool(runtime_payload and runtime_payload.get('ok', False))
            and bool(doctor_payload and doctor_payload.get('ok', False))
            and (config_payload is None or bool(config_payload.get('ok', False)))
        )

    @staticmethod
    def build_message() -> str:
        """
        构建生产巡检统一结果消息。

        :return: 结果消息
        """
        return '生产巡检完成'


@dataclass(frozen=True)
class ProdCheckAggregator:
    """
    `wizard prod-check` 聚合器。

    该对象负责聚合运行环境、应用检查和配置快照结果，
    让 flow 本体只保留交互编排职责。

    :param payload_support: 结果提取支持对象
    :param status_evaluator: 状态评估器
    """

    payload_support: ProdCheckPayloadSupport = ProdCheckPayloadSupport()
    status_evaluator: ProdCheckStatusEvaluator = ProdCheckStatusEvaluator()

    def build_payload(
        self,
        *,
        env: str,
        runtime_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        构建生产巡检聚合结果。

        :param env: 当前运行环境
        :param runtime_payload: 运行环境结果
        :param doctor_payload: 应用检查结果
        :param config_payload: 配置快照结果
        :return: 聚合结果负载
        """
        return {
            'ok': self.status_evaluator.is_ok(runtime_payload, doctor_payload, config_payload),
            'env': env,
            'message': self.status_evaluator.build_message(),
            'runtime': self.payload_support.extract_runtime_payload(runtime_payload),
            'doctor': self.payload_support.extract_doctor_payload(doctor_payload),
            'config': self.payload_support.extract_config_payload(config_payload),
        }
