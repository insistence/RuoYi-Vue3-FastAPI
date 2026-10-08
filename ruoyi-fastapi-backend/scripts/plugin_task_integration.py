import asyncio
import base64
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

TASK_PLUGIN_ID = 'task_demo'
LEGACY_TASK_ID = '0123456789abcdef0123456789abcdef'
LEGACY_CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
EXPECTED_MIGRATIONS = 2


def build_task_artifacts(source: Path, root: Path, trust_file: Path) -> tuple[Path, Path]:
    """
    运行示例交付脚本，签名当前版本及仅用于迁移验收的旧结构夹具。

    :param source: 包含已构建 web/dist 的任务示例源码目录
    :param root: 本次验收专用且尚不存在的输出目录
    :param trust_file: 本次验收使用的临时发布者公钥文件
    :return: 旧结构夹具和当前业务插件的签名制品路径
    """
    import yaml  # noqa: PLC0415
    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415

    from plugins.core.artifacts import build_artifact  # noqa: PLC0415

    if root.exists():
        raise ValueError('Task integration output must be a new directory')
    result = subprocess.run(
        [sys.executable, str(source / 'build_release.py'), '--output', str(root / 'package')],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f'Task package build failed: {result.stderr[-4000:]}')
    current = root / 'package' / TASK_PLUGIN_ID
    manifest = yaml.safe_load((current / 'plugin.yaml').read_text(encoding='utf-8'))
    baseline = root / 'baseline' / TASK_PLUGIN_ID
    baseline.mkdir(parents=True)
    manifest['version'] = '1.0.0'
    manifest['frontend'] = {'delivery': {'type': 'none'}}
    manifest['backend'].pop('health', None)
    manifest['backend']['migrations'] = [
        item for item in manifest['backend']['migrations'] if item.endswith('/001_init.sql')
    ]
    for name in manifest['backend']['migrations']:
        destination = baseline / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current / name, destination)
    (baseline / 'plugin.yaml').write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding='utf-8')
    # 此夹具仅提供 1.0 数据结构；不启动旧业务 API，也不冒充历史发布包。
    (baseline / '__init__.py').write_text(
        'from fastapi import FastAPI\nfrom plugins.core.sdk import PluginDefinition\n'
        'def create_plugin(host):\n    return PluginDefinition(app_factory=lambda context: FastAPI())\n',
        encoding='utf-8',
    )
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    trust = json.loads(trust_file.read_text(encoding='utf-8'))
    trust['keys'].append(
        {'keyId': 'task-integration', 'publicKey': base64.b64encode(public).decode(), 'pluginIds': [TASK_PLUGIN_ID]}
    )
    trust_file.write_text(json.dumps(trust), encoding='utf-8')
    baseline_archive, current_archive = root / 'baseline.rpk', root / 'current.rpk'
    build_artifact(baseline, baseline_archive, key, 'task-integration')
    build_artifact(current, current_archive, key, 'task-integration')
    return baseline_archive, current_archive


async def exercise_task_delivery(service: Any, sessions: Any, source: Path, root: Path) -> dict[str, Any]:
    """
    从受控交付目录验证签名、维护迁移、目标选择、数据保留和真实业务事务。

    :param service: 已注入隔离数据库及生命周期锁的发布服务
    :param sessions: 隔离数据库的异步会话工厂
    :param source: 包含已构建页面的 task_demo 源码目录
    :param root: 当前任务验收专用的新输出目录
    :return: 可用于 CI 输出的验收结果摘要
    """
    from sqlalchemy import select, text  # noqa: PLC0415

    from plugins.core.management.entity.do.models import SysPluginMigration  # noqa: PLC0415

    baseline, current = await asyncio.to_thread(build_task_artifacts, source, root, service.config.trust_file)
    first = await service.catalog.import_artifact(baseline)
    first_prepared = await service.prepare(TASK_PLUGIN_ID, first['digest'], maintenance=True, actor='task-it')
    await service.select(
        TASK_PLUGIN_ID, first['digest'], expected_generation=first_prepared['generation'], maintenance=True
    )
    async with sessions() as db, db.begin():
        await db.execute(
            text(
                'INSERT INTO ruoyi_plugin_task_demo (id, title, description, status, created_at, updated_at) '
                'VALUES (:id, :title, :description, :status, :created, :updated)'
            ),
            {
                'id': LEGACY_TASK_ID,
                'title': '升级前的任务',
                'description': '保留已有业务数据',
                'status': 'todo',
                'created': LEGACY_CREATED_AT,
                'updated': LEGACY_CREATED_AT,
            },
        )
    latest = await service.catalog.import_artifact(current)
    prepared = await service.prepare(TASK_PLUGIN_ID, latest['digest'], maintenance=True, actor='task-it')
    await service.prepare(TASK_PLUGIN_ID, latest['digest'], maintenance=True, actor='task-it')
    selected = await service.select(
        TASK_PLUGIN_ID, latest['digest'], expected_generation=prepared['generation'], maintenance=True
    )
    async with sessions() as db:
        history = (
            await db.scalars(select(SysPluginMigration).where(SysPluginMigration.plugin_id == TASK_PLUGIN_ID))
        ).all()
        if len(history) != EXPECTED_MIGRATIONS or any(
            item.status != 'success' or item.attempt_count != 1 for item in history
        ):
            raise AssertionError('Task migrations must succeed exactly once per database dialect')
    artifact = await service.catalog.get(latest['digest'])
    plugin = service.catalog.discovered(artifact)
    await exercise_task_api(plugin, sessions)
    await service.catalog.get(latest['digest'])
    if list(plugin.backend_path.rglob('*.pyc')):
        raise AssertionError('Task runtime wrote bytecode into the immutable artifact')
    return {
        'pluginId': TASK_PLUGIN_ID,
        'version': artifact.version,
        'digest': latest['digest'],
        'generation': selected['generation'],
        'migrations': len(history),
        'retainedRows': 1,
        'crud': True,
        'readOnlyDenied': True,
    }


async def exercise_task_api(plugin: Any, sessions: Any) -> None:
    """
    从签名交付目录加载当前业务 API，注入权限并验证持久化 CRUD。

    :param plugin: 从签名制品目录发现的任务插件
    :param sessions: 隔离数据库会话工厂
    :return: None
    """
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415

    from plugins.core.runtime.entrypoint import PluginEntrypointLoader  # noqa: PLC0415
    from plugins.core.sdk import PluginHostContext, PluginRequestContext  # noqa: PLC0415

    host = PluginHostContext(TASK_PLUGIN_ID, plugin.backend_path, session_factory=sessions)
    definition = PluginEntrypointLoader(plugin).load(host)
    app = definition.app_factory(host)
    permissions = frozenset({'task_demo:view', 'task_demo:write'})

    @app.middleware('http')
    async def authenticated_fixture(request: Any, call_next: Any) -> Any:
        request.state.plugin_context = PluginRequestContext(host, user=None, permissions=permissions)
        return await call_next(request)

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://task-integration') as client:
        old = await client.get(f'/api/tasks/{LEGACY_TASK_ID}')
        old.raise_for_status()
        retained = old.json()
        if (
            retained['title'] != '升级前的任务'
            or retained['description'] != '保留已有业务数据'
            or retained['status'] != 'todo'
            or retained['priority'] != 'normal'
            or datetime.fromisoformat(retained['createdAt'].replace('Z', '+00:00')) != LEGACY_CREATED_AT
        ):
            raise AssertionError('Task migration changed existing business data')
        permissions = frozenset({'task_demo:view'})
        denied_writes = [
            await client.post('/api/tasks', json={'title': '禁止的写入'}),
            await client.put(f'/api/tasks/{LEGACY_TASK_ID}', json={'title': '禁止的改动'}),
            await client.delete(f'/api/tasks/{LEGACY_TASK_ID}'),
        ]
        if any(response.status_code != HTTPStatus.FORBIDDEN for response in denied_writes):
            raise AssertionError('Read-only role was allowed to mutate a task')
        if (await client.get(f'/api/tasks/{LEGACY_TASK_ID}')).json() != retained:
            raise AssertionError('Denied writes changed the legacy task')
        permissions = frozenset({'task_demo:view', 'task_demo:write'})
        created = await client.post('/api/tasks', json={'title': '升级后新增', 'priority': 'high'})
        created.raise_for_status()
        task_id = created.json()['id']
        updated = await client.put(
            f'/api/tasks/{task_id}',
            json={'title': '升级后更新', 'description': '事务已提交', 'status': 'done', 'priority': 'high'},
        )
        updated.raise_for_status()
        saved = await client.get(f'/api/tasks/{task_id}')
        saved.raise_for_status()
        expected_fields = {'title': '升级后更新', 'description': '事务已提交', 'status': 'done', 'priority': 'high'}
        if any(saved.json()[key] != value for key, value in expected_fields.items()):
            raise AssertionError('Task update did not persist every editable field')
        page = await client.get('/api/tasks', params={'page': 1, 'pageSize': 1, 'status': 'done'})
        page.raise_for_status()
        if page.json()['total'] != 1 or page.json()['items'][0]['id'] != task_id:
            raise AssertionError('Task filtering or pagination lost committed changes')
        deleted = await client.delete(f'/api/tasks/{task_id}')
        deleted.raise_for_status()
        if (await client.get(f'/api/tasks/{task_id}')).status_code != HTTPStatus.NOT_FOUND:
            raise AssertionError('Task deletion was not committed')
        if (await client.get('/api/tasks')).json()['total'] != 1:
            raise AssertionError('CRUD changed the legacy task or committed an unauthorized write')
