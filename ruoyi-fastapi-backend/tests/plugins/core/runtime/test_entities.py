from pathlib import Path

from plugins.core.runtime.entities import EntityModuleImporter

BACKEND_ROOT = Path(__file__).resolve().parents[4]


def test_entity_module_importer_defaults_to_backend_root() -> None:
    """校验实体模块导入器默认使用后端项目根目录。"""
    importer = EntityModuleImporter()

    assert importer.backend_root == BACKEND_ROOT


def write_python_file(file_path: Path, content: str = '') -> Path:
    """写入 Python 测试文件。"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')

    return file_path


def test_entity_module_importer_finds_builtin_entity_do_dirs(tmp_path: Path) -> None:
    """校验实体模块导入器可以发现内置业务模块 entity/do 目录。"""
    backend_root = tmp_path / 'backend'
    entity_do_dir = backend_root / 'module_demo' / 'entity' / 'do'
    entity_do_dir.mkdir(parents=True)
    (backend_root / 'other_demo' / 'entity' / 'do').mkdir(parents=True)

    importer = EntityModuleImporter(backend_root)

    assert importer.get_builtin_entity_do_dirs() == [entity_do_dir]


def test_entity_module_importer_imports_entity_files(tmp_path: Path) -> None:
    """校验实体模块导入器可以导入指定 entity/do 目录中的实体文件。"""
    backend_root = tmp_path / 'backend'
    entity_do_dir = backend_root / 'plugins' / 'importer_demo' / 'entity' / 'do'
    write_python_file(entity_do_dir / 'importer_demo_do.py', 'DEMO_ENTITY_IMPORTED = True\n')
    write_python_file(entity_do_dir / '_private_do.py', 'PRIVATE_ENTITY_IMPORTED = True\n')

    importer = EntityModuleImporter(backend_root)
    imported_modules = importer.import_entity_dirs([entity_do_dir], strict=True)

    assert len(imported_modules) == 1
    assert imported_modules[0].__name__ == 'plugins.importer_demo.entity.do.importer_demo_do'
    assert imported_modules[0].DEMO_ENTITY_IMPORTED is True


def test_entity_module_importer_skips_failed_plugin_import_when_not_strict(tmp_path: Path) -> None:
    """校验插件实体导入失败时非严格模式会跳过失败模块。"""
    backend_root = tmp_path / 'backend'
    entity_do_dir = backend_root / 'plugins' / 'broken' / 'entity' / 'do'
    write_python_file(entity_do_dir / 'broken_do.py', "raise RuntimeError('broken entity')\n")

    importer = EntityModuleImporter(backend_root)

    assert importer.import_plugin_entities([entity_do_dir]) == []
