import json
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from plugins.core.sdk.context import PluginRequestContext

MAX_CACHE_BYTES = 64 * 1024
MAX_CACHE_TTL_SECONDS = 86400


def _require_request(context: PluginRequestContext, plugin_id: str, capability: str) -> int:
    """
    在访问宿主资源前检查插件归属、能力权限和当前用户身份。

    :param context: 宿主签发的请求上下文
    :param plugin_id: 服务绑定的插件 ID
    :param capability: 当前服务要求的插件权限后缀
    :return: 当前登录用户 ID
    """
    if not isinstance(context, PluginRequestContext) or context.host.plugin_id != plugin_id:
        raise PermissionError('请求上下文不属于当前插件')
    context.require_permission(f'{plugin_id}:{capability}')
    user_id = getattr(getattr(context.user, 'user', None), 'user_id', None)
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise PermissionError('缺少有效的当前用户身份')
    return user_id


@asynccontextmanager
async def _request_session(context: PluginRequestContext, factory: Callable[..., Any]) -> AsyncIterator[Any]:
    """
    复用当前任务的显式事务；未开启事务时为单次只读服务创建独立会话。

    :param context: 当前插件请求上下文
    :param factory: 宿主数据库会话工厂
    :return: 当前服务允许使用的数据库会话
    """
    transaction = context.transaction_session()
    if transaction is not None:
        yield transaction
    else:
        async with factory() as db:
            yield db


def build_host_services(
    plugin_id: str, session_factory: Callable[..., Any], redis: Any = None
) -> dict[str, Callable[..., Any]]:
    """
    请求身份只能来自宿主上下文；数据库服务可显式复用当前任务的事务。

    :param plugin_id: 使用宿主服务的插件 ID
    :param session_factory: 创建宿主数据库会话的工厂
    :param redis: 可选的宿主 Redis 客户端，未提供时缓存服务拒绝执行
    :return: 按版本化服务名称索引的宿主服务集合
    """

    async def current_user_profile(context: PluginRequestContext) -> dict[str, Any]:
        """
        验证插件身份和接口权限后读取当前用户资料。

        :param context: 宿主鉴权层建立的插件请求上下文
        :return: 仅包含允许向插件公开字段的当前用户资料
        """
        user_id = _require_request(context, plugin_id, 'profile')

        from module_admin.service.user_service import UserService  # noqa: PLC0415

        async with _request_session(context, session_factory) as db:
            profile = await UserService.user_profile_services(db, user_id)
        if profile.data is None:
            raise LookupError('当前用户不存在')
        # 白名单 DTO，不将 ORM 对象、密码及宿主内部模型协议交给插件。
        return {
            'userId': profile.data.user_id,
            'userName': profile.data.user_name,
            'nickName': profile.data.nick_name,
            'avatar': profile.data.avatar,
            'postGroup': profile.post_group,
            'roleGroup': profile.role_group,
        }

    async def dictionary_items(context: PluginRequestContext, dict_type: str) -> list[dict[str, Any]]:
        """
        读取已启用字典的公开选项，返回不包含宿主 ORM 对象的白名单数据。

        :param context: 当前插件请求上下文
        :param dict_type: 非空字典类型标识
        :return: 按宿主字典顺序排列的选项数据
        """
        _require_request(context, plugin_id, 'dict')
        if not isinstance(dict_type, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,99}', dict_type):
            raise ValueError('字典类型必须是有效的非空标识')
        from module_admin.service.dict_service import DictDataService  # noqa: PLC0415

        async with _request_session(context, session_factory) as db:
            rows = await DictDataService.query_dict_data_list_services(db, dict_type)
            return [
                {
                    'label': row.dict_label,
                    'value': row.dict_value,
                    'cssClass': row.css_class,
                    'listClass': row.list_class,
                    'isDefault': row.is_default == 'Y',
                }
                for row in rows
                if row is not None
            ]

    def cache_key(context: PluginRequestContext, key: str) -> str:
        """
        校验缓存权限并构建固定插件命名空间，不接受通配查询或任意 Redis 命令。

        :param context: 当前插件请求上下文
        :param key: 当前插件内的缓存键
        :return: 带有插件前缀的完整 Redis 键
        """
        _require_request(context, plugin_id, 'cache')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', key):
            raise ValueError('插件缓存键必须是 1 至 128 位字母、数字或 _ . : -')
        if redis is None:
            raise RuntimeError('宿主未提供 Redis 缓存能力')
        return f'plugin:sdk:cache:{plugin_id}:{key}'

    async def cache_get(context: PluginRequestContext, key: str) -> Any:
        """
        获取当前插件的 JSON 缓存，缺失时返回 None。

        :param context: 当前插件请求上下文
        :param key: 当前插件内的缓存键
        :return: 已解码的 JSON 数据或 None
        """
        name = cache_key(context, key)
        value = await redis.get(name)
        if value is None:
            return None
        encoded = value.encode('utf-8') if isinstance(value, str) else value
        if len(encoded) > MAX_CACHE_BYTES:
            raise ValueError('插件缓存内容超过大小限制')
        try:
            result = json.loads(encoded)
            json.dumps(result, allow_nan=False)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError('插件缓存内容不是有效 JSON') from exc
        return result

    async def cache_set(context: PluginRequestContext, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """
        保存有界的 JSON 缓存，必须设置有限有效期；不参与数据库事务。

        :param context: 当前插件请求上下文
        :param key: 当前插件内的缓存键
        :param value: 可序列化的 JSON 数据
        :param ttl_seconds: 有效期秒数，范围为 1 至 86400
        :return: None
        """
        name = cache_key(context, key)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_CACHE_TTL_SECONDS:
            raise ValueError('插件缓存有效期必须在 1 至 86400 秒之间')
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > MAX_CACHE_BYTES:
            raise ValueError('插件缓存内容超过大小限制')
        await redis.set(name, encoded, ex=ttl_seconds)

    async def cache_delete(context: PluginRequestContext, key: str) -> bool:
        """
        删除当前插件的单个缓存键，不提供扫描或批量删除其他插件缓存的能力。

        :param context: 当前插件请求上下文
        :param key: 当前插件内的缓存键
        :return: 是否删除了已有缓存
        """
        name = cache_key(context, key)
        return bool(await redis.delete(name))

    return {
        'users.current_profile.v1': current_user_profile,
        'dictionaries.items.v1': dictionary_items,
        'cache.get.v1': cache_get,
        'cache.set.v1': cache_set,
        'cache.delete.v1': cache_delete,
    }
