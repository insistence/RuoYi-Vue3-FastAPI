from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from plugins.core.manifest.schema import PluginManifest, PluginManifestError, PluginManifestFactory

PLUGIN_MANIFEST_NAME = 'plugin.yaml'
UNSUPPORTED_PLUGIN_MANIFEST_NAMES = ('plugin.yml',)


@dataclass(frozen=True)
class DiscoveredPlugin:
    """
    已发现插件。
    """

    manifest: PluginManifest
    backend_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class PluginDiscoveryError:
    """
    插件发现错误。

    用于在容错扫描模式下记录单个插件加载失败，便于上层隔离损坏插件。
    """

    manifest_path: Path | None
    plugin_dir: Path
    error_message: str


@dataclass(frozen=True)
class PluginDiscoveryResult:
    """
    插件发现结果。

    同时承载成功发现的插件和加载失败明细，避免单个错误插件拖垮整体扫描。
    """

    plugins: list[DiscoveredPlugin] = field(default_factory=list)
    errors: list[PluginDiscoveryError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """
        判断是否存在发现错误。

        :return: 是否存在错误
        """
        return bool(self.errors)


class PluginScanner:
    """
    插件扫描器。

    提供两种扫描语义：

    - :meth:`discover`：严格扫描，任一插件清单错误立即抛出 ``PluginManifestError``。
    - :meth:`discover_with_errors`：容错扫描，逐插件隔离失败，plugin.yml 文件名错误、
      YAML 损坏、清单校验失败等都作为对应插件的错误记录，不影响其他插件。
    """

    def __init__(self, plugins_root: Path | str) -> None:
        """
        初始化插件扫描器。

        :param plugins_root: 后端插件根目录
        """
        self.plugins_root = Path(plugins_root)

    def discover(self) -> list[DiscoveredPlugin]:
        """
        严格扫描插件目录并返回清单校验通过的插件。

        任一插件清单错误（包括 plugin.yml 文件名、YAML 损坏、清单校验失败）都会立即
        抛出 ``PluginManifestError``，保持与历史行为兼容。需要逐插件隔离时请使用
        :meth:`discover_with_errors`。

        :return: 已发现插件列表
        :raises PluginManifestError: 任一插件清单错误
        """
        if not self.plugins_root.exists():
            return []
        self._ensure_plugins_root_is_dir()
        self._reject_unsupported_manifest_names_strict()

        return [
            self.load_manifest(manifest_path)
            for manifest_path in sorted(self.plugins_root.glob(f'*/{PLUGIN_MANIFEST_NAME}'))
        ]

    def discover_with_errors(self) -> PluginDiscoveryResult:
        """
        容错扫描插件目录，返回成功发现的插件及失败明细。

        单个插件的任何错误（plugin.yml 文件名、YAML 损坏、清单校验失败、目录名不一致等）
        都只隔离失败插件，不影响其他正常插件。根目录配置类错误（目录不存在、根路径不是
        目录）仍以异常形式抛出。

        :return: 插件发现结果
        :raises PluginManifestError: 根路径不是目录
        """
        if not self.plugins_root.exists():
            return PluginDiscoveryResult()
        self._ensure_plugins_root_is_dir()

        result = PluginDiscoveryResult()
        # 先收集 plugin.yml 文件名错误，按插件目录隔离
        unsupported_name_errors = self._collect_unsupported_manifest_name_errors()
        result.errors.extend(unsupported_name_errors)
        invalid_plugin_dirs = {error.plugin_dir for error in unsupported_name_errors}
        # 再逐插件加载 plugin.yaml
        for manifest_path in sorted(self.plugins_root.glob(f'*/{PLUGIN_MANIFEST_NAME}')):
            if manifest_path.parent in invalid_plugin_dirs:
                continue
            try:
                result.plugins.append(self.load_manifest(manifest_path))
            except Exception as exc:
                result.errors.append(
                    PluginDiscoveryError(
                        manifest_path=manifest_path,
                        plugin_dir=manifest_path.parent,
                        error_message=str(exc),
                    )
                )
        return result

    def load_manifest(self, manifest_path: Path | str) -> DiscoveredPlugin:
        """
        加载单个插件清单。

        :param manifest_path: 插件清单路径
        :return: 已发现插件
        :raises PluginManifestError: 清单不存在、不是文件、YAML 解析失败或清单校验失败
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
        :raises PluginManifestError: YAML 解析失败或内容不是对象
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

    def _ensure_plugins_root_is_dir(self) -> None:
        """
        校验插件根路径是目录。

        :raises PluginManifestError: 根路径不是目录
        :return: None
        """
        if not self.plugins_root.is_dir():
            raise PluginManifestError(f'插件根路径不是目录：{self.plugins_root}')

    def _reject_unsupported_manifest_names_strict(self) -> None:
        """
        严格模式下检查不支持的插件清单文件名，任一存在立即抛错。

        :raises PluginManifestError: 存在不支持的清单文件名
        :return: None
        """
        for manifest_name in UNSUPPORTED_PLUGIN_MANIFEST_NAMES:
            unsupported_manifest_paths = sorted(self.plugins_root.glob(f'*/{manifest_name}'))
            if unsupported_manifest_paths:
                raise PluginManifestError(
                    f'插件清单文件名必须为 {PLUGIN_MANIFEST_NAME}：{unsupported_manifest_paths[0]}'
                )

    def _collect_unsupported_manifest_name_errors(self) -> list[PluginDiscoveryError]:
        """
        容错模式下收集不支持的清单文件名错误，按插件目录隔离。

        :return: 发现错误列表
        """
        errors: list[PluginDiscoveryError] = []
        for manifest_name in UNSUPPORTED_PLUGIN_MANIFEST_NAMES:
            errors.extend(
                [
                    PluginDiscoveryError(
                        manifest_path=manifest_path,
                        plugin_dir=manifest_path.parent,
                        error_message=f'插件清单文件名必须为 {PLUGIN_MANIFEST_NAME}：{manifest_path}',
                    )
                    for manifest_path in sorted(self.plugins_root.glob(f'*/{manifest_name}'))
                ]
            )
        return errors


def discover_plugins(plugins_root: Path | str) -> list[DiscoveredPlugin]:
    """
    便捷函数：严格扫描插件目录。

    :param plugins_root: 后端插件根目录
    :return: 已发现插件列表
    :raises PluginManifestError: 任一插件清单错误
    """
    return PluginScanner(plugins_root).discover()


def discover_plugins_with_errors(plugins_root: Path | str) -> PluginDiscoveryResult:
    """
    便捷函数：容错扫描插件目录。

    :param plugins_root: 后端插件根目录
    :return: 插件发现结果
    """
    return PluginScanner(plugins_root).discover_with_errors()
