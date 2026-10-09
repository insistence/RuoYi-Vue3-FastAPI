from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from plugins.core.artifacts import build_artifact


@pytest.fixture
def artifact_source(tmp_path: Path) -> Path:
    """构造包含部署文件和禁止导入哨兵的临时插件目录。"""
    source = tmp_path / 'artifact_demo'
    source.mkdir()
    (source / 'plugin.yaml').write_text(
        'manifestVersion: 2\n'
        'id: artifact_demo\n'
        'name: Artifact demonstration\n'
        'version: 1.0.0\n'
        'backend:\n'
        '  runtime: python\n'
        '  integration: router\n'
        '  module: plugins.artifact_demo\n'
        '  entrypoint: plugins.artifact_demo:create_plugin\n'
        'frontend:\n'
        '  delivery:\n'
        '    type: none\n',
        encoding='utf-8',
    )
    (source / '__init__.py').write_text('raise RuntimeError("artifact code must never execute")\n', encoding='utf-8')
    (source / 'LICENSE').write_text('Temporary test fixture.\n', encoding='utf-8')
    (source / 'sql').mkdir()
    (source / 'sql' / 'schema.sql').write_text('SELECT 1;\n', encoding='utf-8')
    return source


@pytest.fixture
def signing_key() -> Ed25519PrivateKey:
    """生成仅用于当前测试的临时 Ed25519 私钥。"""
    return Ed25519PrivateKey.generate()


@pytest.fixture
def trusted_keys(signing_key: Ed25519PrivateKey) -> dict[str, Ed25519PublicKey]:
    """提供与临时签名私钥对应的宿主可信公钥映射。"""
    return {'publisher': signing_key.public_key()}


@pytest.fixture
def artifact_path(tmp_path: Path, artifact_source: Path, signing_key: Ed25519PrivateKey) -> Path:
    """构建供验证和存储测试使用的签名制品。"""
    output = tmp_path / 'sample.rpk'
    build_artifact(artifact_source, output, signing_key, 'publisher')
    return output
