from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.runtime.entities import EntityModuleImporter
from utils.log_util import logger


class PluginEntityImportFailure(BaseModel):
    """
    插件实体导入失败结果。
    """

    plugin_id: str = Field(description='插件ID')
    error_message: str = Field(description='错误信息')


class PluginEntityImportResult(BaseModel):
    """
    插件实体导入结果。
    """

    imported_count: int = Field(default=0, description='成功导入实体模块数量')
    failures: list[PluginEntityImportFailure] = Field(default_factory=list, description='实体导入失败结果列表')


class PluginRuntimeBuilder:
    """
    插件运行时构建器。

    使用 Builder 模式封装插件发现和运行时注册表构建过程，便于后续逐步加入数据库状态、
    依赖检查和生命周期处理。
    """

    def __init__(self, backend_root: Path | str | None = None) -> None:
        """
        初始化插件运行时构建器。

        :param backend_root: 后端项目根目录
        """
        self.backend_root = Path(backend_root) if backend_root else Path(__file__).resolve().parents[2]
        self.plugins_root = self.backend_root / 'plugins'
        self.entity_importer = EntityModuleImporter(self.backend_root)
        self._discovered_plugins: list[DiscoveredPlugin] | None = None

    def discover_plugins(self) -> list[DiscoveredPlugin]:
        """
        发现后端插件。

        :return: 已发现插件列表
        """
        if self._discovered_plugins is not None:
            return self._discovered_plugins
        try:
            self._discovered_plugins = PluginScanner(self.plugins_root).discover()
        except Exception as exc:
            logger.exception(f'插件发现失败：{exc}')
            self._discovered_plugins = []

        return self._discovered_plugins

    def build_registry(self, database_plugins: list[Any] | None = None) -> PluginRegistry:
        """
        构建插件运行时注册表。

        :param database_plugins: 数据库插件状态列表
        :return: 插件运行时注册表
        """
        return PluginRegistry.build(self.discover_plugins(), database_plugins)

    def import_builtin_entities(self) -> None:
        """
        导入内置业务模块实体。

        :return: None
        """
        self.entity_importer.import_builtin_entities()

    def import_plugin_entities(self, plugin_registry: PluginRegistry) -> PluginEntityImportResult:
        """
        导入启用插件实体。

        :param plugin_registry: 插件运行时注册表
        :return: 插件实体导入结果
        """
        import_result = PluginEntityImportResult()
        for plugin in plugin_registry.list_enabled_plugins():
            entity_do_dir = plugin.backend_path / 'entity' / 'do'
            if not entity_do_dir.is_dir():
                continue
            try:
                imported_modules = self.entity_importer.import_entity_dirs([entity_do_dir], strict=True)
                import_result.imported_count += len(imported_modules)
            except Exception as exc:
                logger.exception(f'插件实体导入失败：{plugin.plugin_id}，错误：{exc}')
                import_result.failures.append(
                    PluginEntityImportFailure(plugin_id=plugin.plugin_id, error_message=str(exc))
                )

        return import_result
