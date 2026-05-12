from typing import Any


class CompletionCommandPresenter:
    """
    completion 命令文本渲染器。

    该渲染器负责将 `completion` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_completion_doctor_text(self, payload: dict[str, Any]) -> str:
        """
        将 completion 诊断结果渲染为文本摘要。

        :param payload: completion 诊断结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'active_shell: {payload.get("activeShell") or "-"}',
            f'project_dir: {payload.get("projectDir", "-")}',
            f'complete_env_var: {payload.get("completeEnvVar", "-")}',
        ]
        if payload.get('recommendedInstallCommand'):
            lines.append(f'recommended_install_command: {payload.get("recommendedInstallCommand")}')
        env_choices = payload.get('envChoices')
        if isinstance(env_choices, list) and env_choices:
            lines.append('env_choices:')
            lines.extend(f'  - {env_name}' for env_name in env_choices)
        shells = payload.get('shells')
        if isinstance(shells, dict) and shells:
            lines.append('shells:')
            for shell_name, shell_payload in shells.items():
                if not isinstance(shell_payload, dict):
                    continue
                lines.extend(
                    [
                        f'  {shell_name}:',
                        f'    supported: {str(shell_payload.get("supported", False)).lower()}',
                        f'    detected: {str(shell_payload.get("detected", False)).lower()}',
                        f'    target_file: {shell_payload.get("targetFile", "-")}',
                        f'    target_file_exists: {str(shell_payload.get("targetFileExists", False)).lower()}',
                        f'    rc_file: {shell_payload.get("rcFile", "-") or "-"}',
                        f'    rc_file_exists: {str(shell_payload.get("rcFileExists", False)).lower()}',
                        f'    auto_discovery: {str(shell_payload.get("autoDiscovery", False)).lower()}',
                        f'    source_command: {shell_payload.get("sourceCommand", "-")}',
                        f'    recommended_install_command: {shell_payload.get("recommendedInstallCommand", "-")}',
                    ]
                )
        return '\n'.join(lines)

    @staticmethod
    def build_completion_install_text(payload: dict[str, Any]) -> str:
        """
        将 completion 安装结果渲染为文本摘要。

        :param payload: completion 安装结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'shell: {payload.get("shell", "-")}',
        ]
        field_label_mapping = {
            'detectedShell': 'detected_shell',
            'targetFile': 'target_file',
            'activated': 'activated',
            'activateRequested': 'activate_requested',
            'rcFile': 'rc_file',
            'rcFileUpdated': 'rc_file_updated',
            'sourceCommand': 'source_command',
            'autoDiscovery': 'auto_discovery',
            'activationRequired': 'activation_required',
            'nextStep': 'next_step',
            'completeEnvVar': 'complete_env_var',
        }
        for field_name, field_label in field_label_mapping.items():
            if field_name in payload:
                lines.append(f'{field_label}: {payload.get(field_name)}')
        return '\n'.join(lines)
