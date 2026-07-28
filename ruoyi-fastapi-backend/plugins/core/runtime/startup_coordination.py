from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from config.env import AppConfig

PLUGIN_STARTUP_FINGERPRINT_SUFFIXES = frozenset({'.py', '.sql', '.yaml', '.yml'})


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

        source_files = (
            path
            for path in plugins_root.rglob('*')
            if path.is_file()
            and path.suffix.lower() in PLUGIN_STARTUP_FINGERPRINT_SUFFIXES
            and '__pycache__' not in path.parts
        )
        for source_file in sorted(source_files):
            relative_path = source_file.relative_to(self.backend_root).as_posix()
            digest.update(relative_path.encode())
            digest.update(b'\0')
            digest.update(source_file.read_bytes())
            digest.update(b'\0')

        return digest.hexdigest()[:24]
