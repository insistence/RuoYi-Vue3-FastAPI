from pathlib import Path

from cli.core.app_builder import ProjectRuntimeLocator
from cli.runtime.base import RUNTIME_ENVIRONMENT
from cli.utils import NestedCliProjectLocator


def test_backend_project_dir_detection_uses_consistent_rule(tmp_path: Path) -> None:
    """
    校验不同入口的后端目录判定规则保持一致。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    (tmp_path / 'app.py').write_text('', encoding='utf-8')
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'env.py').write_text('', encoding='utf-8')
    (tmp_path / 'cli').mkdir()

    project_runtime_locator = ProjectRuntimeLocator()
    nested_cli_project_locator = NestedCliProjectLocator()

    assert RUNTIME_ENVIRONMENT.is_backend_project_dir(tmp_path) is True
    assert project_runtime_locator.is_backend_project_dir(tmp_path) is True
    assert nested_cli_project_locator.is_backend_project_dir(tmp_path) is True


def test_backend_project_dir_detection_rejects_directory_without_cli_package(tmp_path: Path) -> None:
    """
    校验缺少 cli 目录时不会被误判为后端项目根目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    (tmp_path / 'app.py').write_text('', encoding='utf-8')
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'env.py').write_text('', encoding='utf-8')

    project_runtime_locator = ProjectRuntimeLocator()
    nested_cli_project_locator = NestedCliProjectLocator()

    assert RUNTIME_ENVIRONMENT.is_backend_project_dir(tmp_path) is False
    assert project_runtime_locator.is_backend_project_dir(tmp_path) is False
    assert nested_cli_project_locator.is_backend_project_dir(tmp_path) is False
