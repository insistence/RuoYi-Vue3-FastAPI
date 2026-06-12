from dataclasses import dataclass
from typing import Literal, TypedDict

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.menu_tree import PluginMenuTree


class PluginDocumentationPayloadDict(TypedDict):
    """
    插件文档生成 payload。
    """

    ok: bool
    message: str
    pluginId: str
    format: Literal['markdown']
    markdown: str
    length: int


@dataclass(frozen=True)
class PluginDocumentationPayload:
    """
    插件文档结构化负载。
    """

    plugin_id: str
    markdown: str

    def to_payload(self) -> PluginDocumentationPayloadDict:
        """
        序列化为现有插件文档 payload 契约。

        :return: 插件文档 payload
        """
        return {
            'ok': True,
            'message': '插件文档生成完成',
            'pluginId': self.plugin_id,
            'format': 'markdown',
            'markdown': self.markdown,
            'length': len(self.markdown),
        }


class PluginDocumentationBuilder:
    """
    插件文档片段构建器。

    使用 Builder 模式将插件 manifest 转换为 Markdown 文档片段，供插件运行时和模板复用。
    """

    @classmethod
    def build_payload(cls, plugin_id: str, discovered_plugin: DiscoveredPlugin) -> PluginDocumentationPayloadDict:
        """
        构建插件文档生成负载。

        :param plugin_id: 插件ID
        :param discovered_plugin: 已发现插件
        :return: 插件文档生成负载
        """
        markdown = cls.build_markdown(discovered_plugin)
        return PluginDocumentationPayload(plugin_id=plugin_id, markdown=markdown).to_payload()

    @classmethod
    def build_markdown(cls, discovered_plugin: DiscoveredPlugin) -> str:
        """
        构建插件 Markdown 文档片段。

        :param discovered_plugin: 已发现插件
        :return: Markdown 文档内容
        """
        manifest = discovered_plugin.manifest
        sections = [
            f'# {manifest.name}',
            '',
            f'- 插件ID：`{manifest.id}`',
            f'- 版本：`{manifest.version}`',
            f'- 默认启用：`{str(manifest.enabled).lower()}`',
            f'- 后端模块：`{manifest.backend.module}`',
            f'- 前端目录：`{manifest.frontend.plugin_id}`',
            f'- 说明：{manifest.description or "-"}',
            '',
            *cls._build_frontend_section(discovered_plugin),
            *cls._build_permission_section(discovered_plugin),
            *cls._build_config_section(discovered_plugin),
            *cls._build_dependency_section(discovered_plugin),
            *cls._build_job_section(discovered_plugin),
            *cls._build_lifecycle_section(discovered_plugin),
            *cls._build_migration_seed_section(discovered_plugin),
        ]

        return '\n'.join(sections).rstrip() + '\n'

    @classmethod
    def _build_frontend_section(cls, discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建前端菜单文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        menus = PluginMenuTree.flatten(discovered_plugin.manifest.frontend.menus)
        lines = ['## 菜单', '']
        if not menus:
            return [*lines, '无菜单声明。', '']

        lines.extend(['| 名称 | 路径 | 组件 | 权限 | 类型 |', '| --- | --- | --- | --- | --- |'])
        lines.extend(
            f'| {menu.name} | `{menu.path}` | `{menu.component}` | `{menu.perms or "-"}` | `{menu.type}` |'
            for menu in menus
        )
        lines.append('')
        return lines

    @staticmethod
    def _build_permission_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建权限文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        permissions = discovered_plugin.manifest.permissions
        lines = ['## 权限', '']
        if not permissions:
            return [*lines, '无权限声明。', '']

        lines.extend(f'- `{permission}`' for permission in permissions)
        lines.append('')
        return lines

    @staticmethod
    def _build_config_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建配置文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        config_items = discovered_plugin.manifest.config.items
        lines = ['## 配置', '']
        if not config_items:
            return [*lines, '无配置声明。', '']

        lines.extend(
            [
                '| Key | 标签 | 类型 | 必填 | 敏感 | 默认值 | 分组 | 说明 |',
                '| --- | --- | --- | --- | --- | --- | --- | --- |',
            ]
        )
        lines.extend(
            '| '
            + ' | '.join(
                [
                    f'`{item.key}`',
                    item.label or '-',
                    f'`{item.type}`',
                    str(item.required).lower(),
                    str(item.secret).lower(),
                    '`******`' if item.secret and item.default is not None else f'`{item.default}`',
                    item.group,
                    item.description or '-',
                ]
            )
            + ' |'
            for item in config_items
        )
        lines.append('')
        return lines

    @staticmethod
    def _build_dependency_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建依赖文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        dependencies = discovered_plugin.manifest.dependencies
        lines = ['## 依赖', '']
        if not dependencies.python and not dependencies.npm and not dependencies.npm_dev and not dependencies.plugins:
            return [*lines, '无依赖声明。', '']

        lines.append('### Python')
        lines.extend(f'- `{item}`' for item in dependencies.python)
        if not dependencies.python:
            lines.append('- 无')
        lines.extend(['', '### NPM'])
        lines.extend(f'- `{item}`' for item in dependencies.npm)
        if not dependencies.npm:
            lines.append('- 无')
        lines.extend(['', '### NPM 开发依赖'])
        lines.extend(f'- `{item}`' for item in dependencies.npm_dev)
        if not dependencies.npm_dev:
            lines.append('- 无')
        lines.extend(['', '### 插件'])
        lines.extend(
            f'- `{item.id}` {item.version or ""} {item.description or ""}'.rstrip() for item in dependencies.plugins
        )
        if not dependencies.plugins:
            lines.append('- 无')
        lines.append('')
        return lines

    @staticmethod
    def _build_job_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建定时任务文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        jobs = discovered_plugin.manifest.backend.jobs
        lines = ['## 定时任务', '']
        if not jobs:
            return [*lines, '无定时任务声明。', '']

        lines.extend(['| ID | 名称 | Callable | Cron | 默认启用 |', '| --- | --- | --- | --- | --- |'])
        lines.extend(
            f'| `{job.id}` | {job.name or "-"} | `{job.callable}` | `{job.cron_expression}` | '
            f'{str(job.enabled).lower()} |'
            for job in jobs
        )
        lines.append('')
        return lines

    @staticmethod
    def _build_lifecycle_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建生命周期文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        hooks = discovered_plugin.manifest.backend.hooks
        hook_items = [
            ('onInstall', hooks.on_install),
            ('onUpgrade', hooks.on_upgrade),
            ('onStartup', hooks.on_startup),
            ('onShutdown', hooks.on_shutdown),
            ('onPurge', hooks.on_purge),
        ]
        lines = ['## 生命周期钩子', '']
        if not any(hook for _, hook in hook_items):
            return [*lines, '无生命周期钩子声明。', '']

        lines.extend(f'- `{name}`：`{hook}`' for name, hook in hook_items if hook)
        lines.append('')
        return lines

    @staticmethod
    def _build_migration_seed_section(discovered_plugin: DiscoveredPlugin) -> list[str]:
        """
        构建 migration 和 seed 文档段落。

        :param discovered_plugin: 已发现插件
        :return: Markdown 行列表
        """
        backend = discovered_plugin.manifest.backend
        lines = ['## Migration 与 Seed', '', '### Migrations']
        lines.extend(f'- `{migration}`' for migration in backend.migrations)
        if not backend.migrations:
            lines.append('- 无')
        lines.extend(['', '### Seeds'])
        lines.extend(f'- `{seed}`' for seed in backend.seeds)
        if not backend.seeds:
            lines.append('- 无')
        lines.append('')
        return lines
