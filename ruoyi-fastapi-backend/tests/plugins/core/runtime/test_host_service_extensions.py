import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from plugins.core.runtime.host_services import MAX_CACHE_BYTES, build_host_services
from plugins.core.sdk import PluginHostContext, PluginRequestContext


def context_for(tmp_path: Path, plugin_id: str = 'sdk_demo', *, permissions: bool = True) -> PluginRequestContext:
    """为字典与缓存服务提供绑定插件的请求身份。"""
    return PluginRequestContext(
        PluginHostContext(plugin_id, tmp_path),
        SimpleNamespace(user=SimpleNamespace(user_id=7)),
        frozenset({f'{plugin_id}:dict', f'{plugin_id}:cache'}) if permissions else frozenset(),
    )


@pytest.mark.asyncio
async def test_dictionary_service_returns_only_public_enabled_options(tmp_path: Path) -> None:
    """调用宿主启用态字典查询，过滤空外连接结果并限制返回字段。"""
    db = object()

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield db

    row = SimpleNamespace(
        dict_label='正常', dict_value='0', css_class='', list_class='success', is_default='Y', remark='private'
    )
    service = build_host_services('sdk_demo', session)['dictionaries.items.v1']
    with patch(
        'module_admin.service.dict_service.DictDataService.query_dict_data_list_services',
        new=AsyncMock(return_value=[row, None]),
    ) as read:
        result = await service(context_for(tmp_path), 'sys_normal_disable')
    read.assert_awaited_once_with(db, 'sys_normal_disable')
    assert result == [{'label': '正常', 'value': '0', 'cssClass': '', 'listClass': 'success', 'isDefault': True}]


@pytest.mark.asyncio
@pytest.mark.parametrize('dict_type', ['', '*', 'sys_type OR 1=1', None, 'a' * 101])
async def test_invalid_dictionary_type_never_queries_database(tmp_path: Path, dict_type: Any) -> None:
    """空类型不能触发宿主的全量字典查询。"""
    session = Mock(side_effect=AssertionError('database must not be touched'))
    service = build_host_services('sdk_demo', session)['dictionaries.items.v1']
    with pytest.raises(ValueError, match='字典类型'):
        await service(context_for(tmp_path), dict_type)
    session.assert_not_called()


@pytest.mark.asyncio
async def test_cache_services_use_plugin_namespace_json_and_bounded_ttl(tmp_path: Path) -> None:
    """同名键按插件隔离，缓存读写使用有界 JSON 和明确 TTL。"""
    redis = SimpleNamespace(
        set=AsyncMock(), get=AsyncMock(return_value=b'{"count":2}'), delete=AsyncMock(return_value=1)
    )
    first = build_host_services('sdk_demo', Mock(), redis)
    second = build_host_services('other_demo', Mock(), redis)
    context = context_for(tmp_path)
    other = context_for(tmp_path, 'other_demo')
    await first['cache.set.v1'](context, 'shared:key', {'count': 2}, 60)
    await second['cache.set.v1'](other, 'shared:key', {'count': 3})
    calls = redis.set.await_args_list
    assert calls[0].args == ('plugin:sdk:cache:sdk_demo:shared:key', b'{"count":2}')
    assert calls[0].kwargs == {'ex': 60}
    assert calls[1].args[0] == 'plugin:sdk:cache:other_demo:shared:key'
    assert calls[1].kwargs == {'ex': 300}
    assert await first['cache.get.v1'](context, 'shared:key') == {'count': 2}
    assert await first['cache.delete.v1'](context, 'shared:key') is True
    redis.delete.assert_awaited_once_with('plugin:sdk:cache:sdk_demo:shared:key')
    redis.get.return_value = None
    assert await first['cache.get.v1'](context, 'missing') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['cache.get.v1', 'cache.set.v1', 'cache.delete.v1', 'dictionaries.items.v1'])
@pytest.mark.parametrize('invalid', ['permission', 'foreign_plugin', 'user'])
async def test_host_services_reject_unauthorized_resource_access(tmp_path: Path, operation: str, invalid: str) -> None:
    """插件、用户与接口权限检查必须先于外部资源调用。"""
    redis = SimpleNamespace(get=AsyncMock(), set=AsyncMock(), delete=AsyncMock())
    session = Mock()
    service = build_host_services('sdk_demo', session, redis)[operation]
    context = context_for(
        tmp_path, 'other_demo' if invalid == 'foreign_plugin' else 'sdk_demo', permissions=invalid != 'permission'
    )
    if invalid == 'user':
        context.user.user.user_id = 0
    arguments = [context, 'example'] + ([{}] if operation == 'cache.set.v1' else [])
    with pytest.raises(PermissionError):
        await service(*arguments)
    session.assert_not_called()
    redis.get.assert_not_awaited()
    redis.set.assert_not_awaited()
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('ttl', [0, -1, 86401, True, 1.5])
async def test_cache_rejects_unbounded_or_invalid_ttl(tmp_path: Path, ttl: Any) -> None:
    """禁止永久缓存及含糊的 TTL 类型。"""
    redis = SimpleNamespace(set=AsyncMock())
    service = build_host_services('sdk_demo', Mock(), redis)['cache.set.v1']
    with pytest.raises(ValueError, match='有效期'):
        await service(context_for(tmp_path), 'valid', {}, ttl)
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('key', ['', '*', '../foreign', 'bad key', 'a' * 129])
async def test_cache_rejects_invalid_keys(tmp_path: Path, key: str) -> None:
    """缓存接口不接受通配符、路径或超长键。"""
    redis = SimpleNamespace(get=AsyncMock())
    with pytest.raises(ValueError, match='缓存键'):
        await build_host_services('sdk_demo', Mock(), redis)['cache.get.v1'](context_for(tmp_path), key)
    redis.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_size_limits_apply_to_reads_and_writes(tmp_path: Path) -> None:
    """受限缓存接口同时约束读写大小，并拒绝损坏的 JSON。"""
    redis = SimpleNamespace(set=AsyncMock(), get=AsyncMock(return_value=b'x' * (MAX_CACHE_BYTES + 1)))
    services = build_host_services('sdk_demo', Mock(), redis)
    context = context_for(tmp_path)
    with pytest.raises(ValueError, match='大小限制'):
        await services['cache.set.v1'](context, 'valid', 'x' * MAX_CACHE_BYTES)
    with pytest.raises(ValueError, match='大小限制'):
        await services['cache.get.v1'](context, 'valid')
    redis.get.return_value = json.dumps({'value': float('nan')})
    with pytest.raises(ValueError, match='有效 JSON'):
        await services['cache.get.v1'](context, 'valid')
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_cache_client_reports_unavailable_capability(tmp_path: Path) -> None:
    """未配置 Redis 时给出明确能力错误。"""
    services = build_host_services('sdk_demo', Mock())
    with pytest.raises(RuntimeError, match='未提供 Redis'):
        await services['cache.get.v1'](context_for(tmp_path), 'valid')
