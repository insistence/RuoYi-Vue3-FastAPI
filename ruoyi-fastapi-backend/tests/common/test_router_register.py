import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from common.router import RouterRegister, auto_register_controller_files, auto_register_routers  # noqa: E402


class RouterRegisterForTest(RouterRegister):
    """
    测试用路由注册器。
    """

    def __init__(self, app: FastAPI, project_root: Path) -> None:
        """
        初始化测试用路由注册器。

        :param app: FastAPI对象
        :param project_root: 测试项目根目录
        """
        super().__init__(app)
        self.project_root = str(project_root)
        sys.path.insert(0, self.project_root)


def touch_file(file_path: Path, content: str = '') -> Path:
    """
    创建测试文件。

    :param file_path: 文件路径
    :param content: 文件内容
    :return: 文件路径
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')

    return file_path


def test_router_register_finds_builtin_controller_files(tmp_path: Path) -> None:
    project_root = tmp_path / 'backend'
    builtin_controller = touch_file(project_root / 'module_demo' / 'controller' / 'demo_controller.py')

    router_register = RouterRegisterForTest(FastAPI(), project_root=project_root)

    controller_files = router_register._find_controller_files()

    assert controller_files == [str(builtin_controller)]


def test_router_register_finds_auto_register_false_controller_files(tmp_path: Path) -> None:
    """
    校验路由注册器仍会发现 controller 文件，是否注册由 APIRouterPro.auto_register 决定。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'backend'
    builtin_controller = touch_file(project_root / 'module_demo' / 'controller' / 'demo_controller.py')
    extra_controller = touch_file(project_root / 'module_extra' / 'controller' / 'extra_controller.py')

    router_register = RouterRegisterForTest(FastAPI(), project_root=project_root)

    assert router_register._find_controller_files() == sorted([str(builtin_controller), str(extra_controller)])


def test_router_register_skips_auto_register_false_router(tmp_path: Path) -> None:
    """
    校验 auto_register=False 的 APIRouterPro 不会被注册到应用。

    :return: None
    """
    project_root = tmp_path / 'backend'
    router_register = RouterRegisterForTest(FastAPI(), project_root=project_root)
    controller_file = touch_file(
        project_root / 'module_test_auto_register' / 'controller' / 'test_controller.py',
        "from common.router import APIRouterPro\ntest_controller = APIRouterPro(prefix='/test', auto_register=False)\n",
    )

    routers = router_register._import_module_and_get_routers([str(controller_file)])

    assert routers == []


def test_router_register_includes_plugin_management_controller() -> None:
    """
    校验内置插件管理 controller 会参与自动注册。

    :return: None
    """
    project_root = BACKEND_ROOT
    router_register = RouterRegisterForTest(FastAPI(), project_root=project_root)

    controller_files = router_register._find_controller_files()

    assert str(project_root / 'module_plugin' / 'controller' / 'plugin_controller.py') in controller_files


def test_auto_register_routers_uses_builtin_controller_registration(monkeypatch: object) -> None:
    """
    校验 auto_register_routers 保持内置 controller 注册语义。

    :param monkeypatch: pytest monkeypatch fixture
    :return: None
    """
    called = []

    class FakeRouterRegister:
        """
        测试用假路由注册器。
        """

        def __init__(self, app: FastAPI) -> None:
            """
            初始化测试用假路由注册器。

            :param app: FastAPI对象
            """
            self.app = app

        def register_routers(self) -> None:
            """
            记录路由注册调用。

            :return: None
            """
            called.append(True)

    monkeypatch.setattr('common.router.RouterRegister', FakeRouterRegister)

    auto_register_routers(FastAPI())

    assert called == [True]


def test_router_register_register_routers_uses_common_controller_file_pipeline(tmp_path: Path) -> None:
    """
    校验内置路由注册复用统一 controller 文件注册流水线。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'backend'
    builtin_controller = touch_file(project_root / 'module_demo' / 'controller' / 'demo_controller.py')
    captured_controller_files = []
    router_register = RouterRegisterForTest(FastAPI(), project_root=project_root)

    def fake_register_controller_files(controller_files: list[str]) -> None:
        """
        记录注册的controller文件。

        :param controller_files: controller文件列表
        :return: None
        """
        captured_controller_files.extend(controller_files)

    router_register._register_controller_files = fake_register_controller_files

    router_register.register_routers()

    assert captured_controller_files == [str(builtin_controller)]


def test_auto_register_controller_files_delegates_to_router_register(monkeypatch: object) -> None:
    """
    校验指定 controller 文件自动注册函数委托给 RouterRegister。

    :param monkeypatch: pytest monkeypatch fixture
    :return: None
    """
    captured_controller_files = []
    captured_dependencies = []

    class FakeRouterRegister:
        """
        测试用假路由注册器。
        """

        def __init__(self, app: FastAPI) -> None:
            """
            初始化测试用假路由注册器。

            :param app: FastAPI对象
            """
            self.app = app

        def _register_controller_files(
            self, controller_files: list[str], dependencies: list[object] | None = None
        ) -> None:
            """
            记录 controller 文件列表。

            :param controller_files: controller文件列表
            :param dependencies: 注册时附加到路由上的依赖项
            :return: None
            """
            captured_controller_files.extend(controller_files)
            captured_dependencies.extend(dependencies or [])

    monkeypatch.setattr('common.router.RouterRegister', FakeRouterRegister)

    dependency = object()
    auto_register_controller_files(FastAPI(), ['demo_controller.py'], dependencies=[dependency])

    assert captured_controller_files == ['demo_controller.py']
    assert captured_dependencies == [dependency]
