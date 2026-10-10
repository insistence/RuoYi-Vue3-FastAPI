import json
import os
import re
from pathlib import Path

FrontendFramework = str

FRONTEND_ROOT_ENV_NAMES = ('RUOYI_PLUGIN_FRONTEND_ROOT', 'RUOYI_FRONTEND_ROOT')
FRONTEND_FRAMEWORK_ENV_NAMES = ('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'RUOYI_FRONTEND_FRAMEWORK')
FRONTEND_FRAMEWORK_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*$')


def validate_frontend_framework(value: str) -> str:
    """
    校验可用于依赖分类和工程目录的前端框架标识。

    auto 仅用于请求自动解析，不能作为实际框架名称。

    :param value: 待校验的前端框架标识
    :return: 校验通过的前端框架标识
    """
    if not isinstance(value, str) or value == 'auto' or FRONTEND_FRAMEWORK_PATTERN.fullmatch(value) is None:
        raise ValueError('frontend_framework 必须以小写字母开头，且仅包含小写字母、数字、下划线或连字符，不能为 auto')
    return value


def resolve_frontend_framework(frontend_framework: str = 'auto') -> FrontendFramework:
    """
    解析前端工程使用的框架标识。

    显式框架优先；auto 模式读取前端框架环境变量，未配置时默认使用 vue3。

    :param frontend_framework: 前端框架标识，auto 表示自动选择
    :return: 解析后的前端框架标识
    """
    framework = (frontend_framework or 'auto').strip().lower()
    if framework == 'auto':
        framework = next(
            (os.environ[name].strip().lower() for name in FRONTEND_FRAMEWORK_ENV_NAMES if os.getenv(name, '').strip()),
            'vue3',
        )
    return validate_frontend_framework(framework)


def resolve_frontend_framework_request(frontend_root: Path | str, requested_framework: str = 'auto') -> str:
    """
    保存前端工程的显式框架选择，供后续依赖、模板与 SDK 按需解析。

    标准工程的 auto 保留目录框架身份；独立工程的 auto 使用已配置的框架
    环境变量，无配置时继续保留 auto，交由包依赖识别。

    :param frontend_root: 已选中的前端工程目录
    :param requested_framework: 请求的框架标识，auto 表示自动识别
    :return: 已规范化并校验的框架请求，可以是 auto
    """
    root = Path(frontend_root)
    framework = (requested_framework or 'auto').strip().lower()
    standard_frontend_root = root.name in {'web', 'mobile'} and root.parent.parent.name == 'ruoyi-fastapi-frontend'
    if framework == 'auto' and not standard_frontend_root:
        framework = next(
            (os.environ[name].strip().lower() for name in FRONTEND_FRAMEWORK_ENV_NAMES if os.getenv(name, '').strip()),
            'auto',
        )
    return framework if framework == 'auto' else validate_frontend_framework(framework)


def select_frontend_root(frontend_root: Path | str, frontend_framework: str = 'auto') -> Path:
    """
    从统一前端目录中选择 Web 工程，保留显式指定的独立工程目录。

    :param frontend_root: 前端工程目录、框架目录或统一前端目录
    :param frontend_framework: 前端框架标识，auto 表示自动选择
    :return: 所选前端工程的绝对路径
    """
    # 仅转换为绝对路径，保留符号链接信息供 SDK 后续执行路径安全检查。
    root = Path(os.path.abspath(frontend_root))
    framework = resolve_frontend_framework(frontend_framework)
    automatic = (frontend_framework or 'auto').strip().lower() == 'auto'
    if root.name == 'web' and root.parent.parent.name == 'ruoyi-fastapi-frontend':
        validate_frontend_framework(root.parent.name)
        # 显式框架选择同级工程，auto 模式保留当前指定的工程。
        return root if automatic else root.parent.parent / framework / 'web'
    if (root / 'package.json').is_file():
        return root
    if root.parent.name == 'ruoyi-fastapi-frontend':
        validate_frontend_framework(root.name)
        return root / 'web' if automatic else root.parent / framework / 'web'
    if root.name == 'ruoyi-fastapi-frontend' or (
        root.is_dir()
        and any(
            path.name != 'auto' and FRONTEND_FRAMEWORK_PATTERN.fullmatch(path.name) and (path / 'web').is_dir()
            for path in root.iterdir()
        )
    ):
        return root / framework / 'web'
    return root


def resolve_frontend_root(
    backend_root: Path | str,
    frontend_root: Path | str | None = None,
    frontend_framework: str = 'auto',
) -> Path:
    """
    解析前端工程根目录。

    依次使用显式目录、环境变量和统一前端目录，并兼容同级的旧版独立前端工程。
    未发现现存工程时，返回统一前端目录下所选框架的 Web 工程路径。

    :param backend_root: 后端项目根目录
    :param frontend_root: 显式指定的前端工程目录或统一前端目录
    :param frontend_framework: 前端框架标识，auto 表示自动选择
    :return: 解析后的前端工程根目录
    """
    backend = Path(backend_root).resolve()
    configured = frontend_root or next(
        (os.environ[name].strip() for name in FRONTEND_ROOT_ENV_NAMES if os.getenv(name, '').strip()), None
    )
    if configured:
        return select_frontend_root(configured, frontend_framework)
    framework = resolve_frontend_framework(frontend_framework)
    container = backend.parent / 'ruoyi-fastapi-frontend'
    if container.is_dir():
        return select_frontend_root(container, framework)
    # 兼容重命名或单独检出的旧版前端工程。
    if backend.parent.is_dir():
        candidates = sorted(
            path
            for path in backend.parent.iterdir()
            if path.is_dir() and path != backend and (path / 'package.json').is_file() and (path / 'plugins').is_dir()
        )
        if candidates:
            return candidates[0]
    return container / framework / 'web'


class PluginFrontendFrameworkResolver:
    """
    前端框架解析器。
    """

    AUTO = 'auto'

    @classmethod
    def resolve(cls, frontend_root: Path, requested_framework: str = AUTO) -> FrontendFramework:
        """
        解析宿主依赖及脚手架应使用的前端框架。

        显式框架优先；标准工程使用目录中的框架标识，独立工程从 package.json
        识别底层框架。无法识别的独立工程要求显式指定。

        :param frontend_root: 前端项目根目录
        :param requested_framework: 前端框架标识，auto 表示自动识别
        :return: 解析后的前端框架标识
        """
        normalized_framework = (requested_framework or cls.AUTO).strip().lower()
        if normalized_framework != cls.AUTO:
            return validate_frontend_framework(normalized_framework)

        # 目录标识决定标准工程的依赖分类，避免被底层 Vue 或 React 包覆盖。
        if frontend_root.name in {'web', 'mobile'} and frontend_root.parent.parent.name == 'ruoyi-fastapi-frontend':
            return validate_frontend_framework(frontend_root.parent.name)

        package_json_path = frontend_root / 'package.json'
        if package_json_path.is_file():
            try:
                package_payload = json.loads(package_json_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f'读取前端 package.json 失败：{package_json_path}（{exc}）') from exc
            if not isinstance(package_payload, dict):
                raise ValueError(f'前端 package.json 顶层必须是对象：{package_json_path}')

            dependencies = cls._collect_dependencies(package_payload)
            vue_version = cls._resolve_vue_dependency(dependencies.get('vue'))
            if vue_version is not None:
                return vue_version
            if 'element-ui' in dependencies:
                return 'vue2'
            if 'element-plus' in dependencies:
                return 'vue3'
            if 'react' in dependencies:
                return 'react'

        raise ValueError(f'无法从 {package_json_path} 识别前端框架，请使用 --frontend-framework 显式指定')

    @staticmethod
    def _collect_dependencies(package_payload: dict[str, object]) -> dict[str, object]:
        """
        合并 dependencies 和 devDependencies。

        :param package_payload: package.json 负载
        :return: 依赖映射
        """
        dependencies: dict[str, object] = {}
        for key in ('devDependencies', 'dependencies'):
            section = package_payload.get(key)
            if isinstance(section, dict):
                dependencies.update(section)
        return dependencies

    @staticmethod
    def _resolve_vue_dependency(version_spec: object) -> FrontendFramework | None:
        """
        从 npm Vue 版本约束中提取主版本。

        :param version_spec: Vue npm 版本约束
        :return: Vue 版本，无法识别时返回 None
        """
        if not isinstance(version_spec, str):
            return None
        match = re.search(r'(?<!\d)([23])(?:\.\d+)?', version_spec)
        if match is None:
            return None
        return f'vue{match.group(1)}'
