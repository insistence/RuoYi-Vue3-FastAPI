import importlib
import sys
from pathlib import Path
from types import ModuleType

from utils.log_util import logger


class EntityModuleImporter:
    """
    实体模块导入器。

    使用 Template Method 模式统一实体文件扫描、模块名转换和导入流程，确保
    SQLAlchemy 在执行 `Base.metadata.create_all` 前可以收集到已启用模块的 DO 元数据。
    """

    def __init__(self, backend_root: Path | str | None = None) -> None:
        """
        初始化实体模块导入器。

        :param backend_root: 后端项目根目录
        """
        self.backend_root = Path(backend_root) if backend_root else Path(__file__).resolve().parents[3]
        self.backend_root = self.backend_root.resolve()
        if str(self.backend_root) not in sys.path:
            sys.path.insert(0, str(self.backend_root))
        self._extend_plugins_package_path()

    def import_builtin_entities(self) -> list[ModuleType]:
        """
        导入内置业务模块实体。

        :return: 已导入模块列表
        """
        return self.import_entity_dirs(self.get_builtin_entity_do_dirs(), strict=True)

    def import_plugin_entities(self, entity_do_dirs: list[Path]) -> list[ModuleType]:
        """
        导入启用插件实体。

        :param entity_do_dirs: 插件 entity/do 目录列表
        :return: 已导入模块列表
        """
        return self.import_entity_dirs(entity_do_dirs, strict=False)

    def get_builtin_entity_do_dirs(self) -> list[Path]:
        """
        获取内置业务模块 entity/do 目录列表。

        :return: 内置 entity/do 目录列表
        """
        return sorted(
            entity_do_dir for entity_do_dir in self.backend_root.glob('module_*/entity/do') if entity_do_dir.is_dir()
        )

    def import_entity_dirs(self, entity_do_dirs: list[Path], strict: bool) -> list[ModuleType]:
        """
        导入指定 entity/do 目录下的实体模块。

        :param entity_do_dirs: entity/do 目录列表
        :param strict: 是否在导入失败时抛出异常
        :return: 已导入模块列表
        """
        imported_modules = []
        for entity_file in self._find_entity_files(entity_do_dirs):
            imported_module = self._import_entity_file(entity_file, strict)
            if imported_module:
                imported_modules.append(imported_module)

        return imported_modules

    def _extend_plugins_package_path(self) -> None:
        """
        扩展已加载 plugins 包的搜索路径。

        :return: None
        """
        plugins_root = self.backend_root / 'plugins'
        if not plugins_root.is_dir():
            return
        try:
            plugins_package = importlib.import_module('plugins')
        except ModuleNotFoundError:
            return
        package_path = getattr(plugins_package, '__path__', None)
        if package_path is not None and str(plugins_root) not in package_path:
            package_path.append(str(plugins_root))

    def _find_entity_files(self, entity_do_dirs: list[Path]) -> list[Path]:
        """
        查找实体文件。

        :param entity_do_dirs: entity/do 目录列表
        :return: 实体文件列表
        """
        entity_files = []
        for entity_do_dir in entity_do_dirs:
            if entity_do_dir.is_dir():
                entity_files.extend(entity_do_dir.glob('[!_]*.py'))

        return sorted(entity_file.resolve() for entity_file in entity_files)

    def _import_entity_file(self, entity_file: Path, strict: bool) -> ModuleType | None:
        """
        导入单个实体文件。

        :param entity_file: 实体文件路径
        :param strict: 是否在导入失败时抛出异常
        :return: 已导入模块，导入失败且非严格模式时返回 None
        """
        module_name = self._to_module_name(entity_file)
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            logger.exception(f'❌ 实体模块导入失败：{module_name}，错误：{exc}')
            if strict:
                raise
            return None

    def _to_module_name(self, entity_file: Path) -> str:
        """
        将实体文件路径转换为 Python 模块路径。

        :param entity_file: 实体文件路径
        :return: Python 模块路径
        """
        relative_path = entity_file.relative_to(self.backend_root)
        module_path = relative_path.with_suffix('')

        return '.'.join(module_path.parts)
