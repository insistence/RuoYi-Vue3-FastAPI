from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProdCheckRenderingSupport:
    """
    `wizard prod-check` 文本渲染支持对象。

    该对象负责构建 runtime、doctor、config 分区文本行，
    避免 presenter 本体继续维护全部分区细节。
    """

    @staticmethod
    def build_runtime_lines(runtime: dict[str, Any]) -> list[str]:
        """
        构建 runtime 分区文本行。

        :param runtime: runtime 结果片段
        :return: 文本行列表
        """
        return [
            'runtime:',
            f'  cli_env: {runtime.get("cliEnv", "-")}',
            f'  config_env: {runtime.get("configEnv", "-")}',
            f'  env_file: {runtime.get("envFile", "-")}',
            f'  env_file_exists: {str(runtime.get("envFileExists", False)).lower()}',
        ]

    @staticmethod
    def build_doctor_lines(doctor: dict[str, Any]) -> list[str]:
        """
        构建 doctor 分区文本行。

        :param doctor: doctor 结果片段
        :return: 文本行列表
        """
        return [
            'doctor:',
            f'  ok: {str(doctor.get("ok", False)).lower()}',
            f'  message: {doctor.get("message", "-")}',
        ]

    @staticmethod
    def build_config_lines(config: dict[str, Any]) -> list[str]:
        """
        构建 config 分区文本行。

        :param config: config 结果片段
        :return: 文本行列表
        """
        return [
            'config:',
            f'  name: {config.get("name", "-")}',
            f'  host: {config.get("host", "-")}:{config.get("port", "-")}',
            f'  db_type: {config.get("dbType", "-")}',
            f'  redis_host: {config.get("redisHost", "-")}:{config.get("redisPort", "-")}',
        ]


@dataclass(frozen=True)
class ProdCheckPresenter:
    """
    `wizard prod-check` 结果展示器。

    该对象负责将聚合结果转换为文本摘要，
    避免在 flow 内继续维护文本渲染细节。

    :param rendering_support: 文本渲染支持对象
    """

    rendering_support: ProdCheckRenderingSupport = ProdCheckRenderingSupport()

    def build_text(self, payload: dict[str, Any]) -> str:
        """
        将生产巡检聚合结果渲染为文本摘要。

        :param payload: 聚合结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "-")}',
            f'message: {payload.get("message", "-")}',
        ]
        runtime = payload.get('runtime')
        if isinstance(runtime, dict):
            lines.extend(self.rendering_support.build_runtime_lines(runtime))
        doctor = payload.get('doctor')
        if isinstance(doctor, dict):
            lines.extend(self.rendering_support.build_doctor_lines(doctor))
        config = payload.get('config')
        if isinstance(config, dict):
            lines.extend(self.rendering_support.build_config_lines(config))
        return '\n'.join(lines)
