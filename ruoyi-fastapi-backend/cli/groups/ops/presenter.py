from cli.utils import SHELL_TEXT_FORMATTER


class OpsCommandPresenter:
    """
    运维命令文本渲染器。

    该渲染器负责将 `ops` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_health_text(self, payload: dict[str, object]) -> str:
        """
        将基础健康检查结果渲染为文本摘要。

        :param payload: 健康检查结果字典
        :return: 文本摘要
        """
        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'env: {payload.get("env", "")}',
                'checks:',
                self._build_check_status_line('database', payload.get('database')),
                self._build_check_status_line('redis', payload.get('redis')),
            ]
        )

    def build_server_info_text(self, payload: dict[str, object]) -> str:
        """
        将服务器运行时信息渲染为文本摘要。

        :param payload: 服务器运行时信息结果字典
        :return: 文本摘要
        """
        server = payload.get('server')
        if not isinstance(server, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    'server: none',
                ]
            )

        sys_info = server.get('sys')
        cpu_info = server.get('cpu')
        mem_info = server.get('mem')
        py_info = server.get('py')
        sys_files = server.get('sysFiles')

        lines = [f'ok: {str(payload.get("ok", False)).lower()}']
        if isinstance(sys_info, dict):
            lines.extend(
                [
                    'host:',
                    f'  name: {sys_info.get("computerName", "-")}',
                    f'  ip: {sys_info.get("computerIp", "-")}',
                    f'  os: {SHELL_TEXT_FORMATTER.truncate_text(sys_info.get("osName", "-"), 90)}',
                    f'  arch: {sys_info.get("osArch", "-")}',
                    f'  user_dir: {SHELL_TEXT_FORMATTER.truncate_text(sys_info.get("userDir", "-"), 100)}',
                ]
            )

        if isinstance(cpu_info, dict):
            lines.extend(
                [
                    'cpu:',
                    f'  cores: {cpu_info.get("cpuNum", "-")}',
                    f'  used: {cpu_info.get("used", "-")}%',
                    f'  sys: {cpu_info.get("sys", "-")}%',
                    f'  free: {cpu_info.get("free", "-")}%',
                ]
            )

        if isinstance(mem_info, dict):
            lines.extend(
                [
                    'memory:',
                    f'  total: {mem_info.get("total", "-")}',
                    f'  used: {mem_info.get("used", "-")}',
                    f'  free: {mem_info.get("free", "-")}',
                    f'  usage: {mem_info.get("usage", "-")}%',
                ]
            )

        if isinstance(py_info, dict):
            lines.extend(
                [
                    'python:',
                    f'  name: {py_info.get("name", "-")}',
                    f'  version: {py_info.get("version", "-")}',
                    f'  start_time: {py_info.get("startTime", "-")}',
                    f'  run_time: {py_info.get("runTime", "-")}',
                    f'  home: {SHELL_TEXT_FORMATTER.truncate_text(py_info.get("home", "-"), 100)}',
                    f'  process_memory: {py_info.get("used", "-")} / {py_info.get("total", "-")} ({py_info.get("usage", "-")}%)',
                ]
            )

        if isinstance(sys_files, list):
            lines.append(f'disks: {len(sys_files)}')
            if sys_files:
                lines.append('disk_samples:')
                lines.extend(
                    f'  - {item.get("dirName", "-")} | used: {item.get("used", "-")} / {item.get("total", "-")} | usage: {item.get("usage", "-")}'
                    for item in sys_files[:10]
                    if isinstance(item, dict)
                )

        return '\n'.join(lines)

    def build_dependencies_text(self, payload: dict[str, object]) -> str:
        """
        将依赖版本检查结果渲染为文本摘要。

        :param payload: 依赖版本检查结果字典
        :return: 文本摘要
        """
        packages = payload.get('packages')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'include_dev: {str(payload.get("includeDev", False)).lower()}',
        ]
        missing_required = payload.get('missingRequired')
        if isinstance(missing_required, list) and missing_required:
            lines.append('missing_required:')
            lines.extend(f'  - {item}' for item in missing_required)
        else:
            lines.append('missing_required: none')

        if not isinstance(packages, dict) or not packages:
            lines.append('packages: none')
            return '\n'.join(lines)

        lines.append('packages:')
        for package_name in sorted(packages):
            dependency_payload = packages.get(package_name)
            if isinstance(dependency_payload, dict):
                lines.append(self._build_dependency_line(package_name, dependency_payload))
        return '\n'.join(lines)

    @staticmethod
    def _build_check_status_line(name: str, status_payload: dict[str, object] | None) -> str:
        """
        构建单项检查结果摘要行。

        :param name: 检查项名称
        :param status_payload: 检查结果字典
        :return: 摘要行文本
        """
        if not isinstance(status_payload, dict):
            return f'  {name}: unknown'

        ok = str(status_payload.get('ok', False)).lower()
        message = status_payload.get('message', '-') or '-'
        error = status_payload.get('error')
        if error:
            return f'  {name}: {ok} | {message} | error: {SHELL_TEXT_FORMATTER.truncate_text(error, 120)}'
        return f'  {name}: {ok} | {message}'

    @staticmethod
    def _build_dependency_line(name: str, dependency_payload: dict[str, object] | None) -> str:
        """
        构建单个依赖项的文本摘要行。

        :param name: 依赖项名称
        :param dependency_payload: 依赖项结果字典
        :return: 文本摘要行
        """
        if not isinstance(dependency_payload, dict):
            return f'  {name}: not-installed'

        installed = str(dependency_payload.get('installed', False)).lower()
        version = dependency_payload.get('version', '-') or '-'
        required = str(dependency_payload.get('required', False)).lower()
        distribution = dependency_payload.get('distribution', '') or name
        return f'  {name}: {installed} | version: {version} | required: {required} | dist: {distribution}'
