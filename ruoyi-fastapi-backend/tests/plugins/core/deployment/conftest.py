import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.menu_do import SysMenu
from plugins.core.artifacts import build_artifact
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.management.entity.do.models import (
    SysPlugin,
    SysPluginConfig,
    SysPluginMenu,
    SysPluginMigration,
    SysPluginOperationLog,
)
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker


@pytest_asyncio.fixture
async def deployment_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """创建包含发布及必要宿主表的临时 SQLite 会话工厂。"""
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "deployment.sqlite"}')
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                item.__table__
                for item in (
                    SysPlugin,
                    SysPluginArtifact,
                    SysPluginRelease,
                    SysPluginWorker,
                    SysPluginConfig,
                    SysPluginMenu,
                    SysPluginMigration,
                    SysPluginOperationLog,
                    SysMenu,
                    SysJob,
                )
            ],
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def deployment_key() -> Ed25519PrivateKey:
    """生成发布测试使用的临时签名私钥。"""
    return Ed25519PrivateKey.generate()


@pytest.fixture
def deployment_config(tmp_path: Path, deployment_key: Ed25519PrivateKey) -> PluginDeploymentConfig:
    """构造独立存储目录与受限发布者公钥配置。"""
    backend = tmp_path / 'host'
    (backend / 'plugins').mkdir(parents=True)
    trust_file = tmp_path / 'trusted-publishers.json'
    public_key = deployment_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    trust_file.write_text(
        json.dumps(
            {
                'schemaVersion': 1,
                'keys': [
                    {
                        'keyId': 'publisher',
                        'publicKey': base64.b64encode(public_key).decode(),
                        'pluginIds': ['artifact_demo'],
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    return PluginDeploymentConfig(backend, tmp_path / 'store', trust_file)


@pytest.fixture
def deployment_source(tmp_path: Path) -> Path:
    """创建用于验证静态维护边界的临时部署目录。"""
    source = tmp_path / 'artifact_demo'
    source.mkdir()
    (source / 'plugin.yaml').write_text(
        'manifestVersion: 2\n'
        'id: artifact_demo\n'
        'name: Signed deployment fixture\n'
        'version: 1.0.0\n'
        'backend:\n'
        '  module: plugins.artifact_demo\n'
        '  entrypoint: plugins.artifact_demo:create_plugin\n'
        'frontend:\n'
        '  delivery:\n'
        '    type: none\n',
        encoding='utf-8',
    )
    (source / '__init__.py').write_text(
        'raise RuntimeError("Static release checks must never import plugin code")\n'
        'def create_plugin(context):\n'
        '    raise RuntimeError("The injected maintenance runtime owns lifecycle execution")\n',
        encoding='utf-8',
    )
    return source


@pytest.fixture
def deployment_archive(tmp_path: Path, deployment_source: Path, deployment_key: Ed25519PrivateKey) -> Path:
    """构建发布服务测试使用的签名制品。"""
    path = tmp_path / 'deployment.rpk'
    build_artifact(deployment_source, path, deployment_key, 'publisher')
    return path
