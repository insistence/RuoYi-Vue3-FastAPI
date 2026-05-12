class DevCommandPresenter:
    """
    开发命令文本渲染器。

    该渲染器负责将 `dev` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_dev_lint_text(self, payload: dict[str, object]) -> str:
        """
        将 lint 执行结果渲染为文本摘要。

        :param payload: lint 执行结果字典
        :return: 文本摘要
        """
        targets = payload.get('targets')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'check_only: {str(payload.get("checkOnly", False)).lower()}',
            f'fix: {str(payload.get("fix", False)).lower()}',
            f'unsafe_fixes: {str(payload.get("unsafeFixes", False)).lower()}',
        ]
        if isinstance(targets, list) and targets:
            lines.append('targets:')
            lines.extend(f'  - {target}' for target in targets)
        else:
            lines.append('targets: none')
        lines.extend(self._build_command_result_section('format', payload.get('format')))
        lines.extend(self._build_command_result_section('check', payload.get('check')))
        return '\n'.join(lines)

    def build_dev_test_text(self, payload: dict[str, object]) -> str:
        """
        将测试执行结果渲染为文本摘要。

        :param payload: 测试执行结果字典
        :return: 文本摘要
        """
        targets = payload.get('targets')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'keyword: {payload.get("keyword", "") or "-"}',
            f'maxfail: {payload.get("maxfail", 0)}',
            f'quiet: {str(payload.get("quiet", False)).lower()}',
        ]
        if isinstance(targets, list) and targets:
            lines.append('targets:')
            lines.extend(f'  - {target}' for target in targets)
        else:
            lines.append('targets: none')
        lines.extend(self._build_command_result_section('test', payload.get('test')))
        return '\n'.join(lines)

    @staticmethod
    def _build_command_result_section(title: str, payload: dict[str, object] | None) -> list[str]:
        """
        构建单个子命令执行结果段落。

        :param title: 段落标题
        :param payload: 子命令执行结果
        :return: 文本行列表
        """
        if not isinstance(payload, dict):
            return [f'{title}: none']

        lines = [
            f'{title}:',
            f'  ok: {str(payload.get("ok", False)).lower()}',
            f'  return_code: {payload.get("returnCode", "-")}',
            f'  command: {DevCommandPresenter._format_command_text(payload.get("command"))}',
        ]
        stdout = payload.get('stdout')
        stderr = payload.get('stderr')
        if stdout:
            lines.append('  stdout:')
            lines.append('    |')
            lines.extend(f'      {line}' for line in str(stdout).splitlines())
        if stderr:
            lines.append('  stderr:')
            lines.append('    |')
            lines.extend(f'      {line}' for line in str(stderr).splitlines())
        return lines

    @staticmethod
    def _format_command_text(command: object) -> str:
        """
        将命令参数列表格式化为可读文本。

        :param command: 命令参数列表
        :return: 格式化后的命令文本
        """
        if not isinstance(command, list):
            return '-'
        return ' '.join(str(item) for item in command) or '-'
