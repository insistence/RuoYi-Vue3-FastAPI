from cli.utils import SHELL_TEXT_FORMATTER


class CacheCommandPresenter:
    """
    缓存命令文本渲染器。

    该渲染器负责将 `cache` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_cache_stats_text(self, payload: dict[str, object]) -> str:
        """
        将缓存统计结果渲染为文本摘要。

        :param payload: 缓存统计结果
        :return: 文本摘要
        """
        info = payload.get('info')
        command_stats = payload.get('commandStats')
        cache_names = payload.get('cacheNames')

        redis_version = '-'
        connected_clients = '-'
        used_memory = '-'
        uptime_seconds = '-'
        keyspace_hits = '-'
        keyspace_misses = '-'
        if isinstance(info, dict):
            redis_version = info.get('redis_version', '-')
            connected_clients = info.get('connected_clients', '-')
            used_memory = info.get('used_memory_human', info.get('used_memory', '-'))
            uptime_seconds = info.get('uptime_in_seconds', '-')
            keyspace_hits = info.get('keyspace_hits', '-')
            keyspace_misses = info.get('keyspace_misses', '-')

        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'db_size: {payload.get("dbSize", 0)}',
            'redis:',
            f'  version: {redis_version}',
            f'  connected_clients: {connected_clients}',
            f'  used_memory: {used_memory}',
            f'  uptime_seconds: {uptime_seconds}',
            f'  keyspace_hits: {keyspace_hits}',
            f'  keyspace_misses: {keyspace_misses}',
        ]

        if isinstance(command_stats, list) and command_stats:
            lines.append('command_stats_top10:')
            lines.extend(
                f'  - {item.get("name", "-")}: {item.get("value", 0)}'
                for item in command_stats[:10]
                if isinstance(item, dict)
            )
        else:
            lines.append('command_stats_top10: none')

        if isinstance(cache_names, list) and cache_names:
            lines.append(f'cache_names: {len(cache_names)}')
            lines.append('cache_name_samples:')
            lines.extend(
                f'  - {item.get("cacheName", "-")}: {self._build_cache_name_remark(item.get("remark", ""))}'
                for item in cache_names[:10]
                if isinstance(item, dict)
            )
        else:
            lines.append('cache_names: 0')

        return '\n'.join(lines)

    def build_cache_keys_text(self, payload: dict[str, object]) -> str:
        """
        将缓存键列表结果渲染为文本摘要。

        :param payload: 缓存键列表结果
        :return: 文本摘要
        """
        keys = payload.get('keys')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'cache_name: {payload.get("cacheName", "")}',
            f'count: {payload.get("count", 0)}',
        ]
        if not isinstance(keys, list) or not keys:
            lines.append('keys: none')
            return '\n'.join(lines)

        lines.append('keys:')
        lines.extend(f'  - {key}' for key in keys)
        return '\n'.join(lines)

    def build_cache_value_text(self, payload: dict[str, object]) -> str:
        """
        将缓存值读取结果渲染为文本摘要。

        :param payload: 缓存值读取结果字典
        :return: 文本摘要
        """
        cache_value = '' if payload.get('cacheValue') is None else str(payload.get('cacheValue'))
        cache_value_lines = cache_value.splitlines() if cache_value else []
        if not cache_value_lines:
            rendered_value_lines = ['  -']
        elif len(cache_value_lines) == 1:
            rendered_value_lines = [f'  {SHELL_TEXT_FORMATTER.truncate_text(cache_value_lines[0], 200)}']
        else:
            rendered_value_lines = ['  |', *[f'    {line}' for line in cache_value_lines]]

        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'cache_name: {payload.get("cacheName", "")}',
                f'cache_key: {payload.get("cacheKey", "")}',
                f'full_cache_key: {payload.get("fullCacheKey", "")}',
                'cache_value:',
                *rendered_value_lines,
            ]
        )

    @staticmethod
    def build_cache_ttl_text(payload: dict[str, object]) -> str:
        """
        将缓存 TTL 结果渲染为文本摘要。

        :param payload: 缓存 TTL 结果字典
        :return: 文本摘要
        """
        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'cache_name: {payload.get("cacheName", "")}',
                f'cache_key: {payload.get("cacheKey", "")}',
                f'full_cache_key: {payload.get("fullCacheKey", "")}',
                f'message: {payload.get("message", "-")}',
                f'ttl_seconds: {payload.get("ttlSeconds", "-")}',
                f'persistent: {str(payload.get("persistent", False)).lower()}',
                f'expires: {str(payload.get("expires", False)).lower()}',
            ]
        )

    @staticmethod
    def _build_cache_name_remark(remark: object) -> str:
        """
        规范化缓存名称备注文本。

        :param remark: 原始备注
        :return: 规范化后的备注
        """
        text = '' if remark is None else str(remark).strip()
        return text or '-'
