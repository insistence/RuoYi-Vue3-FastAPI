from collections.abc import Callable
from typing import Any

from plugins.core.sdk.context import PluginRequestContext


def build_host_services(plugin_id: str, session_factory: Callable[..., Any]) -> dict[str, Callable[..., Any]]:
    """
    请求身份只能来自宿主上下文；服务自己创建和释放数据库会话。

    :param plugin_id: 使用宿主服务的插件 ID
    :param session_factory: 创建宿主数据库会话的工厂
    :return: 按版本化服务名称索引的宿主服务集合
    """

    async def current_user_profile(context: PluginRequestContext) -> dict[str, Any]:
        """
        验证插件身份和接口权限后读取当前用户资料。

        :param context: 宿主鉴权层建立的插件请求上下文
        :return: 仅包含允许向插件公开字段的当前用户资料
        """
        if not isinstance(context, PluginRequestContext) or context.host.plugin_id != plugin_id:
            raise PermissionError('请求上下文不属于当前插件')
        context.require_permission(f'{plugin_id}:profile')
        user_id = getattr(getattr(context.user, 'user', None), 'user_id', None)
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise PermissionError('缺少有效的当前用户身份')

        from module_admin.service.user_service import UserService  # noqa: PLC0415

        async with session_factory() as db:
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

    return {'users.current_profile.v1': current_user_profile}
