from hashlib import sha256
from pathlib import Path

from config.env import AppConfig
from plugins.core.discovery.scanner import PluginScanner

PLUGIN_STARTUP_FINGERPRINT_SUFFIXES = frozenset(
    {'.py', '.sql', '.yaml', '.yml', '.pyd', '.so', '.whl', '.dll', '.dylib'}
)
FINGERPRINT_CHUNK_SIZE = 1024 * 1024


class PluginStartupGenerationResolver:
    """
    插件启动代际解析器。

    生产部署可通过 ``APP_RELEASE_ID`` 显式提供发布代际。未配置时，对应用版本和插件
    后端源码生成稳定指纹，使同一发布的多个 worker 共享代际，而源码变化后的滚动发布
    不会复用旧版本 ready 状态。
    """

    def __init__(self, backend_root: Path | str, *, release_id: str | None = None) -> None:
        """
        初始化插件启动代际解析器。

        :param backend_root: 后端项目根目录
        :param release_id: 显式发布标识
        """
        self.backend_root = Path(backend_root).resolve()
        self.release_id = release_id if release_id is not None else AppConfig.app_release_id

    def resolve(self) -> str:
        """
        解析当前插件启动代际。

        :return: 可用于 Redis key 的稳定代际摘要
        """
        digest = sha256()
        explicit_release_id = self.release_id.strip()
        if explicit_release_id:
            digest.update(b'release:')
            digest.update(explicit_release_id.encode())
            return digest.hexdigest()[:24]

        digest.update(f'app-version:{AppConfig.app_version}\n'.encode())
        plugins_root = self.backend_root / 'plugins'
        if not plugins_root.is_dir():
            return digest.hexdigest()[:24]

        # 开发示例及其构建缓存不参与宿主发布代际，也不递归遍历该目录。
        source_roots = (path for path in plugins_root.iterdir() if path.name != 'examples')
        source_files = (
            path
            for source_root in source_roots
            for path in (
                source_root.rglob('*') if source_root.is_dir() and not source_root.is_symlink() else (source_root,)
            )
            if path.is_file()
            and path.suffix.lower() in PLUGIN_STARTUP_FINGERPRINT_SUFFIXES
            and '__pycache__' not in path.parts
        )
        files = set(source_files)
        # 在不可变制品索引接入前，按清单精确覆盖 bundle 和 native 安装目录。
        # 不把上传数据、日志、pycache 等可变内容计入发布代际。
        for plugin in PluginScanner(plugins_root).discover_with_errors().plugins:
            if not plugin.manifest.uses_entrypoint:
                continue
            resource_dirs = []
            if plugin.manifest.runtime_kind == 'native':
                resource_dirs.append(plugin.backend_path / plugin.manifest.backend.native.module_root)
            if plugin.manifest.frontend.delivery.type == 'bundle':
                resource_dirs.append(plugin.backend_path / plugin.manifest.frontend.bundle.directory)
            for resource_dir in resource_dirs:
                if not resource_dir.resolve().is_relative_to(plugin.backend_path.resolve()):
                    continue
                files.update(
                    path
                    for path in resource_dir.rglob('*')
                    if path.is_file()
                    and '__pycache__' not in path.parts
                    and path.resolve().is_relative_to(plugin.backend_path.resolve())
                )
        for source_file in sorted(files):
            relative_path = source_file.relative_to(self.backend_root).as_posix()
            digest.update(relative_path.encode())
            digest.update(b'\0')
            with source_file.open('rb') as stream:
                for chunk in iter(lambda: stream.read(FINGERPRINT_CHUNK_SIZE), b''):
                    digest.update(chunk)
            digest.update(b'\0')

        return digest.hexdigest()[:24]
