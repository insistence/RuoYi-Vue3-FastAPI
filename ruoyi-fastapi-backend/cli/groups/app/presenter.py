from typing import Any

from cli.utils import SHELL_TEXT_FORMATTER


class AppCommandPresenter:
    """
    应用命令文本渲染器。

    该渲染器负责将 `app` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_routes_text(self, payload: dict[str, Any]) -> str:
        """
        将路由列表结果渲染为文本摘要。

        :param payload: 路由列表结果字典
        :return: 文本摘要
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            f'count: {payload.get("count", 0)}',
        ]
        filters = payload.get('filters')
        if isinstance(filters, dict):
            lines.extend(self._build_route_filter_lines(filters))

        grouped_routes = payload.get('groupedRoutes')
        if filters and filters.get('groupBy') == 'tag' and isinstance(grouped_routes, dict):
            lines.extend(self._build_grouped_routes_text(grouped_routes))
            return '\n'.join(lines)

        routes = payload.get('routes')
        if not isinstance(routes, list) or not routes:
            lines.append('routes: none')
            return '\n'.join(lines)

        lines.append('routes:')
        for route in routes:
            if isinstance(route, dict):
                lines.extend([f'  {line}' for line in self._build_route_item_lines(route)])
        return '\n'.join(lines)

    def build_app_config_text(self, payload: dict[str, Any]) -> str:
        """
        将应用配置快照渲染为文本摘要。

        :param payload: 应用配置结果字典
        :return: 文本摘要
        """
        config = payload.get('config')
        if not isinstance(config, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'env: {payload.get("env", "")}',
                    'config: none',
                ]
            )

        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'env: {payload.get("env", "")}',
            'application:',
            f'  name: {config.get("name", "-")}',
            f'  host: {config.get("host", "-")}:{config.get("port", "-")}',
            f'  root_path: {config.get("rootPath", "-") or "/"}',
            f'  reload: {str(config.get("reload", False)).lower()}',
            f'  workers: {config.get("workers", "-")}',
            f'  disable_swagger: {str(config.get("disableSwagger", False)).lower()}',
            f'  disable_redoc: {str(config.get("disableRedoc", False)).lower()}',
            'database:',
            f'  type: {config.get("dbType", "-")}',
            f'  host: {config.get("dbHost", "-")}:{config.get("dbPort", "-")}',
            f'  name: {config.get("dbDatabase", "-")}',
            'redis:',
            f'  host: {config.get("redisHost", "-")}:{config.get("redisPort", "-")}',
            'logging:',
            f'  level: {config.get("logLevel", "-")}',
            'transport_crypto:',
            f'  enabled: {str(config.get("transportCryptoEnabled", False)).lower()}',
            f'  mode: {config.get("transportCryptoMode", "-")}',
        ]
        return '\n'.join(lines)

    def build_app_env_text(self, payload: dict[str, Any]) -> str:
        """
        将应用环境解析结果渲染为文本摘要。

        :param payload: 应用环境结果字典
        :return: 文本摘要
        """
        runtime = payload.get('runtime')
        if not isinstance(runtime, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'env: {payload.get("env", "")}',
                    'runtime: none',
                ]
            )

        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'env: {payload.get("env", "")}',
                'runtime:',
                f'  cli_env: {runtime.get("cliEnv", "-")}',
                f'  config_env: {runtime.get("configEnv", "-")}',
                f'  app_env: {runtime.get("appEnv", "-")}',
                f'  env_file: {runtime.get("envFile", "-")}',
                f'  env_file_exists: {str(runtime.get("envFileExists", False)).lower()}',
                f'  backend_dir: {runtime.get("backendDir", "-")}',
                f'  python_executable: {runtime.get("pythonExecutable", "-")}',
            ]
        )

    def build_doctor_text(self, payload: dict[str, Any]) -> str:
        """
        将应用启动前检查结果渲染为文本摘要。

        :param payload: 启动前检查结果字典
        :return: 文本摘要
        """
        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'env: {payload.get("env", "")}',
                'checks:',
                self._build_check_status_line('database', payload.get('database')),
                self._build_check_status_line('redis', payload.get('redis')),
                self._build_check_status_line('crypto', payload.get('crypto')),
            ]
        )

    @staticmethod
    def _build_route_filter_lines(filters: dict[str, object]) -> list[str]:
        """
        构建路由过滤条件文本行。

        :param filters: 过滤条件字典
        :return: 过滤条件文本行列表
        """
        active_filters = []
        for key, value in filters.items():
            if value in (None, '', False, 'none'):
                continue
            active_filters.append(f'{SHELL_TEXT_FORMATTER.to_snake_case(key)}={value}')
        if not active_filters:
            return ['filters: none']
        return ['filters:', *[f'  - {item}' for item in active_filters]]

    @staticmethod
    def _build_route_item_lines(route_item: dict[str, Any]) -> list[str]:
        """
        构建单条路由记录的文本行。

        :param route_item: 单条路由记录
        :return: 文本行列表
        """
        methods = ','.join(route_item.get('methods', [])) or '-'
        path = SHELL_TEXT_FORMATTER.truncate_text(route_item.get('path', ''), 72)
        tags = ','.join(route_item.get('tags', [])) or '-'
        summary = SHELL_TEXT_FORMATTER.truncate_text(route_item.get('summary', ''), 60)
        name = SHELL_TEXT_FORMATTER.truncate_text(route_item.get('name', ''), 40)
        return [
            f'- [{methods}] {path}',
            f'  name: {name or "-"} | tags: {tags}',
            f'  summary: {summary or "-"}',
        ]

    def _build_grouped_routes_text(self, grouped_routes: dict[str, Any]) -> list[str]:
        """
        将按标签分组后的路由结果渲染为文本行。

        :param grouped_routes: 按标签分组后的路由映射
        :return: 文本行列表
        """
        if not grouped_routes:
            return ['groups: none']

        lines = [f'groups: {len(grouped_routes)}']
        for tag, routes in grouped_routes.items():
            route_items = routes if isinstance(routes, list) else []
            lines.append(f'  {tag}: {len(route_items)}')
            for route in route_items:
                if isinstance(route, dict):
                    lines.extend([f'    {line}' for line in self._build_route_item_lines(route)])
        return lines

    @staticmethod
    def _build_check_status_line(name: str, status_payload: dict[str, Any] | None) -> str:
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
