from .naming import PluginScaffoldNaming
from .options import PluginScaffoldOptions


class PluginBackendScaffoldTemplateBuilder:
    """
    后端插件模板内容构建器。
    """

    @staticmethod
    def build_manifest(plugin_id: str, options: PluginScaffoldOptions) -> str:
        """
        构建后端插件清单内容。

        :param plugin_id: 插件ID
        :param options: 插件模板生成选项
        :return: 后端插件清单内容
        """
        migrations = ' []' if not options.migration else '\n    - migrations/001_init.sql'
        seeds = ' []' if not options.seed else '\n    - seeds/001_seed.sql'
        jobs = (
            ' []'
            if not options.job
            else f"""
    - id: heartbeat
      name: {plugin_id} 心跳
      callable: plugins.{plugin_id}.jobs.heartbeat
      trigger: cron
      cronExpression: '0 0/30 * * * ?'
      enabled: false
      description: {plugin_id} 插件定时任务声明示例"""
        )
        config = (
            ''
            if not options.config
            else """

config:
  items:
    - key: enabled_feature
      label: 示例开关
      type: boolean
      default: true
      required: false
      description: 示例插件开关
    - key: api_key
      label: 示例密钥
      type: password
      default: ''
      required: false
      secret: true
      description: 敏感配置示例，请在安装后填写"""
        )
        frontend_menus = (
            f"""
  menus:
    - name: {plugin_id}
      path: {plugin_id}
      component: plugin/{plugin_id}/index
      perms: {plugin_id}:list
      type: C
      icon: '#'"""
            if options.frontend
            else """
  menus: []"""
        )
        return f"""id: {plugin_id}
name: {plugin_id}
version: 0.1.0
description: {plugin_id} 插件

backend:
  module: plugins.{plugin_id}
  routers:
    autoScan: true
  migrations:{migrations}
  seeds:{seeds}
  hooks:
    onInstall: hooks:on_install
    onUpgrade: hooks:on_upgrade
    onStartup: hooks:on_startup
    onShutdown: hooks:on_shutdown
    onPurge: hooks:on_purge
  jobs:{jobs}

frontend:
  basePath: {plugin_id}
  pluginId: {plugin_id}
  viewsPath: views
  apiPath: api
{frontend_menus}

permissions:
  - {plugin_id}:list

dependencies:
  python: []
  npm: []
  npmDev: []
  plugins: []
{config}
"""

    @staticmethod
    def build_controller(plugin_id: str) -> str:
        """
        构建后端控制器模板内容。

        :param plugin_id: 插件ID
        :return: 后端控制器模板内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""from common.router import APIRouterPro

from plugins.{plugin_id}.service.{plugin_id}_service import {service_class_name}Service

router = APIRouterPro(prefix='/{plugin_id}', tags=['{plugin_id}'])


@router.get('/ping')
async def ping() -> dict[str, str]:
    \"\"\"
    插件探活接口。

    :return: 插件探活结果
    \"\"\"
    return {service_class_name}Service.ping()
"""

    @staticmethod
    def build_crud_controller(plugin_id: str) -> str:
        """
        构建后端 CRUD 控制器模板内容。

        :param plugin_id: 插件ID
        :return: 后端 CRUD 控制器模板内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""from common.router import APIRouterPro

from plugins.{plugin_id}.service.{plugin_id}_service import {service_class_name}Service

router = APIRouterPro(prefix='/{plugin_id}', tags=['{plugin_id}'])


@router.get('/ping')
async def ping() -> dict[str, str]:
    \"\"\"
    插件探活接口。

    :return: 插件探活结果
    \"\"\"
    return {service_class_name}Service.ping()


@router.get('/items')
async def list_items(keyword: str = '') -> dict[str, object]:
    \"\"\"
    查询示例数据列表。

    :param keyword: 名称关键字
    :return: 示例数据分页结果
    \"\"\"
    return {service_class_name}Service.list_items(keyword)


@router.post('/items')
async def create_item(payload: dict[str, object]) -> dict[str, object]:
    \"\"\"
    创建示例数据。

    :param payload: 示例数据负载
    :return: 创建后的示例数据
    \"\"\"
    return {service_class_name}Service.create_item(payload)


@router.put('/items/{{item_id}}')
async def update_item(item_id: int, payload: dict[str, object]) -> dict[str, object]:
    \"\"\"
    更新示例数据。

    :param item_id: 示例数据ID
    :param payload: 示例数据负载
    :return: 更新后的示例数据
    \"\"\"
    return {service_class_name}Service.update_item(item_id, payload)


@router.delete('/items/{{item_id}}')
async def delete_item(item_id: int) -> dict[str, object]:
    \"\"\"
    删除示例数据。

    :param item_id: 示例数据ID
    :return: 删除结果
    \"\"\"
    return {service_class_name}Service.delete_item(item_id)
"""

    @staticmethod
    def build_service(plugin_id: str) -> str:
        """
        构建后端服务模板内容。

        :param plugin_id: 插件ID
        :return: 后端服务模板内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""class {service_class_name}Service:
    \"\"\"
    {plugin_id} 插件服务。
    \"\"\"

    @classmethod
    def ping(cls) -> dict[str, str]:
        \"\"\"
        返回插件探活结果。

        :return: 插件探活结果
        \"\"\"
        return {{'message': '{plugin_id} plugin ok'}}
"""

    @staticmethod
    def build_crud_service(plugin_id: str) -> str:
        """
        构建后端 CRUD 服务模板内容。

        :param plugin_id: 插件ID
        :return: 后端 CRUD 服务模板内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""class {service_class_name}Service:
    \"\"\"
    {plugin_id} 插件 CRUD 示例服务。

    第一版模板使用内存数据演示 controller/service 分层，实际业务可替换为 dao/entity 实现。
    \"\"\"

    _items = [
        {{'itemId': 1, 'itemName': '{plugin_id} 示例', 'status': '0', 'remark': '插件 CRUD 模板数据'}},
    ]

    @classmethod
    def ping(cls) -> dict[str, str]:
        \"\"\"
        返回插件探活结果。

        :return: 插件探活结果
        \"\"\"
        return {{'message': '{plugin_id} plugin ok'}}

    @classmethod
    def list_items(cls, keyword: str = '') -> dict[str, object]:
        \"\"\"
        查询示例数据列表。

        :param keyword: 名称关键字
        :return: 示例数据分页结果
        \"\"\"
        rows = [
            item
            for item in cls._items
            if not keyword or keyword.lower() in str(item.get('itemName', '')).lower()
        ]
        return {{'rows': rows, 'total': len(rows)}}

    @classmethod
    def create_item(cls, payload: dict[str, object]) -> dict[str, object]:
        \"\"\"
        创建示例数据。

        :param payload: 示例数据负载
        :return: 创建后的示例数据
        \"\"\"
        next_id = max([int(item['itemId']) for item in cls._items], default=0) + 1
        item = {{
            'itemId': next_id,
            'itemName': str(payload.get('itemName') or '未命名'),
            'status': str(payload.get('status') or '0'),
            'remark': str(payload.get('remark') or ''),
        }}
        cls._items.append(item)
        return item

    @classmethod
    def update_item(cls, item_id: int, payload: dict[str, object]) -> dict[str, object]:
        \"\"\"
        更新示例数据。

        :param item_id: 示例数据ID
        :param payload: 示例数据负载
        :return: 更新后的示例数据
        \"\"\"
        for item in cls._items:
            if item['itemId'] != item_id:
                continue
            item.update(
                {{
                    'itemName': str(payload.get('itemName') or item.get('itemName')),
                    'status': str(payload.get('status') or item.get('status')),
                    'remark': str(payload.get('remark') or ''),
                }}
            )
            return item
        return {{'itemId': item_id, 'itemName': '', 'status': '1', 'remark': 'not found'}}

    @classmethod
    def delete_item(cls, item_id: int) -> dict[str, object]:
        \"\"\"
        删除示例数据。

        :param item_id: 示例数据ID
        :return: 删除结果
        \"\"\"
        before_count = len(cls._items)
        cls._items = [item for item in cls._items if item['itemId'] != item_id]
        return {{'deleted': len(cls._items) < before_count, 'itemId': item_id}}
"""

    @staticmethod
    def build_hooks(plugin_id: str) -> str:
        """
        构建后端生命周期钩子模板内容。

        :param plugin_id: 插件ID
        :return: 后端生命周期钩子模板内容
        """
        return f"""from plugins.core.runtime.hooks import PluginHookContext
from utils.log_util import logger


async def on_install(context: PluginHookContext) -> None:
    \"\"\"
    插件安装生命周期钩子。

    :param context: 插件生命周期钩子上下文
    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin install hook executed')


async def on_upgrade(context: PluginHookContext) -> None:
    \"\"\"
    插件升级生命周期钩子。

    :param context: 插件生命周期钩子上下文
    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin upgrade hook executed')


async def on_startup(context: PluginHookContext) -> None:
    \"\"\"
    插件启动生命周期钩子。

    :param context: 插件生命周期钩子上下文
    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin startup hook executed')


async def on_shutdown(context: PluginHookContext) -> None:
    \"\"\"
    插件关闭生命周期钩子。

    :param context: 插件生命周期钩子上下文
    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin shutdown hook executed')


async def on_purge(context: PluginHookContext) -> None:
    \"\"\"
    插件物理清理生命周期钩子。

    :param context: 插件生命周期钩子上下文
    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin purge hook executed')
"""

    @staticmethod
    def build_jobs(plugin_id: str) -> str:
        """
        构建后端定时任务模板内容。

        :param plugin_id: 插件ID
        :return: 后端定时任务模板内容
        """
        return f"""from utils.log_util import logger


def heartbeat() -> None:
    \"\"\"
    插件心跳定时任务。

    :return: None
    \"\"\"
    logger.info('{plugin_id} plugin heartbeat job executed')
"""

    @staticmethod
    def build_migration(plugin_id: str) -> str:
        """
        构建后端 migration 模板内容。

        :param plugin_id: 插件ID
        :return: 后端 migration 模板内容
        """
        return f"""-- {plugin_id} plugin initial migration.
-- Add plugin tables or schema changes here.
"""

    @staticmethod
    def build_seed(plugin_id: str) -> str:
        """
        构建后端 seed 模板内容。

        :param plugin_id: 插件ID
        :return: 后端 seed 模板内容
        """
        return f"""-- {plugin_id} plugin initial seed.
-- Add idempotent initialization data here.
"""

    @staticmethod
    def build_test(plugin_id: str) -> str:
        """
        构建后端插件 pytest 样例。

        :param plugin_id: 插件ID
        :return: 后端插件测试样例内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""from plugins.{plugin_id}.service.{plugin_id}_service import {service_class_name}Service


def test_{plugin_id}_service_ping() -> None:
    \"\"\"
    校验插件服务探活返回稳定负载。

    :return: None
    \"\"\"
    assert {service_class_name}Service.ping() == {{'message': '{plugin_id} plugin ok'}}
"""

    @staticmethod
    def build_crud_test(plugin_id: str) -> str:
        """
        构建后端插件 CRUD pytest 样例。

        :param plugin_id: 插件ID
        :return: 后端插件 CRUD 测试样例内容
        """
        service_class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""from plugins.{plugin_id}.service.{plugin_id}_service import {service_class_name}Service


def test_{plugin_id}_service_ping() -> None:
    \"\"\"
    校验插件服务探活返回稳定负载。

    :return: None
    \"\"\"
    assert {service_class_name}Service.ping() == {{'message': '{plugin_id} plugin ok'}}


def test_{plugin_id}_service_crud_flow() -> None:
    \"\"\"
    校验插件 CRUD 示例服务返回稳定负载。

    :return: None
    \"\"\"
    created = {service_class_name}Service.create_item({{'itemName': '测试数据', 'status': '0'}})
    listed = {service_class_name}Service.list_items('测试')
    updated = {service_class_name}Service.update_item(created['itemId'], {{'itemName': '测试数据2'}})
    deleted = {service_class_name}Service.delete_item(created['itemId'])

    assert listed['total'] >= 1
    assert updated['itemName'] == '测试数据2'
    assert deleted['deleted'] is True
"""

    @staticmethod
    def build_readme(plugin_id: str) -> str:
        """
        构建后端 README 内容。

        :param plugin_id: 插件ID
        :return: 后端 README 内容
        """
        return f"""# {plugin_id} backend plugin

Backend plugin scaffold generated by `ruoyi plugin create`.

## Structure

- `plugin.yaml`: backend manifest, menus, permissions and dependencies.
- `controller/`: FastAPI routers discovered when the plugin is enabled.
- `service/`: plugin service classes.
- `dao/`: plugin data access classes.
- `entity/do/`: SQLAlchemy models imported before table creation.
- `entity/vo/`: Pydantic request and response models.
- `hooks.py`: lifecycle hook examples declared in `plugin.yaml`.
- `jobs.py`: scheduled job example declared in `plugin.yaml`.
- `migrations/`: database migration scripts declared in `plugin.yaml`.
- `seeds/`: initialization scripts declared in `plugin.yaml`.
- `tests/plugins/{plugin_id}/`: pytest examples for this plugin.
- frontend project `tests/plugins/{plugin_id}/`: frontend node tests for this plugin.

## Commands

```bash
ruoyi plugin check {plugin_id}
pytest tests/plugins/{plugin_id}
cd <frontend-project> && node tests/plugins/{plugin_id}/pluginView.test.js
ruoyi plugin install {plugin_id} --dry-run
ruoyi plugin install {plugin_id} --yes
ruoyi plugin enable {plugin_id} --yes
ruoyi plugin disable {plugin_id} --yes
ruoyi plugin upgrade {plugin_id} --dry-run
ruoyi plugin uninstall {plugin_id} --yes
ruoyi plugin purge {plugin_id} --dry-run
ruoyi plugin config get {plugin_id}
```

## Frontend View

The menu component `plugin/{plugin_id}/index` maps to:

```text
<frontend-project>/plugins/{plugin_id}/views/index.vue
```
"""
