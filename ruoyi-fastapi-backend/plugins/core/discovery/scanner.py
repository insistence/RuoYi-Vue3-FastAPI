from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from plugins.core.manifest.schema import PluginManifest, PluginManifestError, PluginManifestFactory

PLUGIN_MANIFEST_NAME = 'plugin.yaml'
UNSUPPORTED_PLUGIN_MANIFEST_NAMES = {'plugin.yml'}


@dataclass(frozen=True)
class DiscoveredPlugin:
    """
    已发现插件。
    """

    manifest: PluginManifest
    backend_path: Path
    manifest_path: Path


class PluginScanner:
    """
    插件扫描器。
    """

    def __init__(self, plugins_root: Path | str) -> None:
        """
        初始化插件扫描器。

        :param plugins_root: 后端插件根目录
        """
        self.plugins_root = Path(plugins_root)

    def discover(self) -> list[DiscoveredPlugin]:
        """
        扫描插件目录并返回清单校验通过的插件。

        :return: 已发现插件列表
        """
        if not self.plugins_root.exists():
            return []
        if not self.plugins_root.is_dir():
            raise PluginManifestError(f'插件根路径不是目录：{self.plugins_root}')

        self._reject_unsupported_manifest_names()

        return [
            self.load_manifest(manifest_path)
            for manifest_path in sorted(self.plugins_root.glob(f'*/{PLUGIN_MANIFEST_NAME}'))
        ]

    def load_manifest(self, manifest_path: Path | str) -> DiscoveredPlugin:
        """
        加载单个插件清单。

        :param manifest_path: 插件清单路径
        :return: 已发现插件
        """
        current_manifest_path = Path(manifest_path)
        if not current_manifest_path.exists():
            raise PluginManifestError(f'插件清单不存在：{current_manifest_path}')
        if not current_manifest_path.is_file():
            raise PluginManifestError(f'插件清单不是文件：{current_manifest_path}')

        raw_manifest = self._read_yaml(current_manifest_path)
        try:
            manifest = PluginManifestFactory.create(raw_manifest)
        except ValidationError as exc:
            error_summary = self._format_validation_errors(exc)
            raise PluginManifestError(f'插件清单校验失败：{current_manifest_path}，{error_summary}') from exc

        backend_path = current_manifest_path.parent
        if backend_path.name != manifest.id:
            raise PluginManifestError(f'插件目录名必须与插件 id 一致：目录={backend_path.name}，id={manifest.id}')

        return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=current_manifest_path)

    @staticmethod
    def _read_yaml(manifest_path: Path) -> dict[str, Any]:
        """
        读取 YAML 清单文件。

        :param manifest_path: 插件清单路径
        :return: YAML 解析后的字典
        """
        try:
            with manifest_path.open('r', encoding='utf-8') as manifest_file:
                data = yaml.safe_load(manifest_file) or {}
        except yaml.YAMLError as exc:
            raise PluginManifestError(f'插件清单 YAML 解析失败：{manifest_path}') from exc

        if not isinstance(data, dict):
            raise PluginManifestError(f'插件清单必须是 YAML 对象：{manifest_path}')
        return data

    @staticmethod
    def _format_validation_errors(exc: ValidationError, *, limit: int = 5) -> str:
        """
        格式化 Pydantic 字段校验错误摘要。

        :param exc: Pydantic 校验异常
        :param limit: 最大错误数量
        :return: 错误摘要
        """
        formatted_errors = []
        for error in exc.errors()[:limit]:
            location = '.'.join(str(part) for part in error.get('loc', ())) or '<root>'
            message = error.get('msg', '校验失败')
            formatted_errors.append(f'{location}: {message}')

        remaining_count = max(0, len(exc.errors()) - limit)
        if remaining_count:
            formatted_errors.append(f'另有 {remaining_count} 个错误')

        return '；'.join(formatted_errors)

    def _reject_unsupported_manifest_names(self) -> None:
        """
        检查不支持的插件清单文件名。

        :return: None
        """
        for manifest_name in UNSUPPORTED_PLUGIN_MANIFEST_NAMES:
            unsupported_manifest_paths = sorted(self.plugins_root.glob(f'*/{manifest_name}'))
            if unsupported_manifest_paths:
                raise PluginManifestError(
                    f'插件清单文件名必须为 {PLUGIN_MANIFEST_NAME}：{unsupported_manifest_paths[0]}'
                )


def discover_plugins(plugins_root: Path | str) -> list[DiscoveredPlugin]:
    """
    便捷函数：扫描插件目录。

    :param plugins_root: 后端插件根目录
    :return: 已发现插件列表
    """
    return PluginScanner(plugins_root).discover()
