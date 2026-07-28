from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from plugins.core.capability import STATE_CHANGE_OPERATIONS, PluginRuntimeCapabilityResolver
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.environment import PLUGIN_RUNTIME_ENVIRONMENT
from plugins.core.lifecycle.jobs import PluginJobInstaller, PluginJobRepository
from plugins.core.lifecycle.purge import PluginPurgePlan, PluginPurgePlanner
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.entity.vo.schemas import (
    PluginConfigModel,
    PluginConfigUpdateModel,
    PluginConfigValueModel,
    PluginMenuModel,
    PluginMigrationModel,
    PluginModel,
    PluginOperationLogDetailModel,
    PluginOperationLogExportQueryModel,
    PluginOperationLogModel,
    PluginOperationLogPageQueryModel,
    PluginOperationLogRetentionModel,
    PluginOperationLogRetentionResultModel,
    PluginPageQueryModel,
    PluginStatus,
)
from plugins.core.management.service.config import PluginConfigManager
from plugins.core.management.service.logs import PluginOperationLogBuilder
from plugins.core.management.service.menus import PluginMenuInstaller
from plugins.core.manifest.menu_tree import PluginMenuTree
from plugins.core.state import PluginStateResolver, PluginStateSnapshot, PluginStateTransitionTable
from plugins.core.validation.dependencies import PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX
from plugins.core.validation.menus import PluginMenuConflictItem
from utils.common_util import CamelCaseUtil
from utils.excel_util import ExcelUtil
from utils.page_util import PageUtil


class PluginService:
    """
    插件系统服务层。
    """

    ORPHAN_PLUGIN_REASON = '插件源码不存在，仅允许物理清理平台元数据'

    @classmethod
    async def get_plugin_list_services(cls, query_db: AsyncSession) -> list[PluginModel]:
        """
        获取插件列表。

        :param query_db: orm对象
        :return: 插件信息列表
        """
        plugin_list = await PluginDao.get_plugin_list(query_db)

        return [PluginModel(**CamelCaseUtil.transform_result(plugin)) for plugin in plugin_list]

    @classmethod
    async def get_plugin_page_list_services(
        cls,
        query_db: AsyncSession,
        query_object: PluginPageQueryModel,
        is_page: bool = True,
        *,
        backend_root: Path | None = None,
        frontend_root: Path | None = None,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取插件分页列表。

        :param query_db: orm对象
        :param query_object: 插件分页查询对象
        :param is_page: 是否开启分页
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件分页列表或插件列表
        """
        backend_root = backend_root or Path(PLUGIN_RUNTIME_ENVIRONMENT.get_backend_plugins_dir())
        frontend_root = frontend_root or Path(PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_plugins_dir())
        discovered_plugins = PluginScanner(backend_root).discover()
        database_plugins = await PluginDao.get_plugin_list(query_db)
        database_plugin_map = {plugin.plugin_id: plugin for plugin in database_plugins}
        discovered_plugin_ids = {plugin.manifest.id for plugin in discovered_plugins}
        plugin_items = [
            cls._build_plugin_model(
                discovered_plugin,
                backend_root,
                frontend_root,
                database_plugin_map.get(discovered_plugin.manifest.id),
            ).model_dump(by_alias=True)
            for discovered_plugin in discovered_plugins
        ]
        plugin_items.extend(
            cls._build_orphan_plugin_model(plugin).model_dump(by_alias=True)
            for plugin in database_plugins
            if plugin.plugin_id not in discovered_plugin_ids
        )
        plugin_items = cls._filter_plugin_page_items(plugin_items, query_object)

        if is_page:
            return PageUtil.get_page_obj(plugin_items, query_object.page_num, query_object.page_size)

        return plugin_items

    @classmethod
    async def plugin_detail_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        *,
        backend_root: Path | None = None,
        frontend_root: Path | None = None,
    ) -> PluginModel | None:
        """
        获取插件详情。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件信息对象
        """
        backend_root = backend_root or Path(PLUGIN_RUNTIME_ENVIRONMENT.get_backend_plugins_dir())
        frontend_root = frontend_root or Path(PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_plugins_dir())
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        discovered_plugin = cls._get_discovered_plugin(backend_root, plugin_id)
        if discovered_plugin:
            return cls._build_plugin_model(discovered_plugin, backend_root, frontend_root, plugin)

        return cls._build_orphan_plugin_model(plugin) if plugin else None

    @classmethod
    async def upsert_discovered_plugin_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        backend_root: Path,
        frontend_root: Path | None = None,
    ) -> PluginModel:
        """
        写入或更新已发现插件。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件信息对象
        """
        manifest = discovered_plugin.manifest
        existing_plugin = await PluginDao.get_plugin_by_id(query_db, manifest.id)
        plugin_model = cls._build_plugin_model(discovered_plugin, backend_root, frontend_root, existing_plugin)

        if existing_plugin:
            await PluginDao.update_plugin(query_db, PluginDao.dump_plugin_persistence_payload(plugin_model))
        else:
            await PluginDao.add_plugin(query_db, plugin_model)

        return plugin_model

    @classmethod
    async def update_plugin_enabled_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> CrudResponseModel:
        """
        更新插件启停状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件对象，用于启用时恢复声明任务
        :return: 操作响应
        """
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        if not plugin:
            return CrudResponseModel(is_success=False, message='插件不存在')
        if enabled and not getattr(plugin, 'installed_version', None):
            return CrudResponseModel(is_success=False, message='插件尚未安装，不能启用')

        operation = 'enable' if enabled else 'disable'
        status = PluginStateTransitionTable.resolve_target(getattr(plugin, 'status', None), operation)
        if status is None:
            return CrudResponseModel(is_success=False, message='插件状态不允许执行当前启停操作')
        enabled_value = PluginStateResolver.enabled_to_db_value(enabled)
        update_payload = {
            'plugin_id': plugin_id,
            'enabled': enabled_value,
            'status': status,
            'update_time': datetime.now(),
        }
        if enabled:
            update_payload['last_error'] = None
        await PluginDao.update_plugin(query_db, update_payload)
        await PluginMenuInstaller(query_db).set_plugin_menu_status(plugin_id, '0' if enabled else '1')
        job_installer = PluginJobInstaller(query_db)
        if enabled and discovered_plugin:
            await job_installer.install_plugin_jobs(discovered_plugin, enabled=True)
        elif not enabled:
            await job_installer.pause_plugin_jobs(plugin_id)

        return CrudResponseModel(is_success=True, message='启用成功' if enabled else '停用成功')

    @classmethod
    async def mark_plugin_installed_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginModel:
        """
        标记插件安装完成。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件信息对象
        """
        manifest = discovered_plugin.manifest
        plugin = await PluginDao.get_plugin_by_id(query_db, manifest.id)
        enabled = getattr(plugin, 'enabled', None) if plugin else '0'
        status = PluginStateTransitionTable.resolve_target(getattr(plugin, 'status', None), 'install') or 'installed'
        update_payload = {
            'plugin_id': manifest.id,
            'version': manifest.version,
            'installed_version': manifest.version,
            'status': status,
            'last_error': None,
            'update_time': datetime.now(),
        }
        await PluginDao.update_plugin(query_db, update_payload)

        return PluginModel(
            pluginId=manifest.id,
            pluginName=manifest.name,
            version=manifest.version,
            installedVersion=manifest.version,
            enabled=enabled,
            status=status,
            source='local',
            backendPath=str(discovered_plugin.backend_path),
            description=manifest.description,
            updateTime=update_payload['update_time'],
        )

    @classmethod
    async def mark_plugin_uninstalled_services(cls, query_db: AsyncSession, plugin_id: str) -> CrudResponseModel:
        """
        标记插件已卸载。

        卸载不同于停用：停用保留 installed_version，卸载清空安装版本，使本地插件回到可安装状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 操作响应
        """
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        if not plugin:
            return CrudResponseModel(is_success=False, message='插件不存在')

        plugin_menus = await PluginDao.get_plugin_menu_list(query_db, plugin_id)
        menu_ids = [plugin_menu.menu_id for plugin_menu in plugin_menus]
        update_payload = {
            'plugin_id': plugin_id,
            'installed_version': None,
            'enabled': '1',
            'status': 'discovered',
            'last_error': None,
            'update_time': datetime.now(),
        }
        await PluginDao.update_plugin(query_db, update_payload)
        await PluginDao.delete_plugin_menus(query_db, plugin_id)
        await PluginDao.delete_sys_menus_by_ids(query_db, menu_ids)
        await PluginJobInstaller(query_db).pause_plugin_jobs(plugin_id)

        return CrudResponseModel(is_success=True, message='卸载成功')

    @classmethod
    async def install_plugin_menu_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        enabled: bool,
    ) -> None:
        """
        安装指定插件菜单并设置菜单启停状态。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param enabled: 插件菜单是否启用
        :return: None
        """
        menu_installer = PluginMenuInstaller(query_db)
        await menu_installer.install_manifest_menus(discovered_plugin.manifest)
        await menu_installer.set_plugin_menu_status(discovered_plugin.manifest.id, '0' if enabled else '1')

    @classmethod
    async def install_plugin_default_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> list[PluginConfigModel]:
        """
        安装插件默认配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件配置模型列表
        """
        installed_configs = []
        manifest = discovered_plugin.manifest
        existing_configs = await PluginDao.get_plugin_config_list(query_db, manifest.id)
        existing_config_map = {config.config_key: config for config in existing_configs}
        desired_config_keys = {item.key for item in manifest.config.items}
        for item in manifest.config.items:
            existing_config = existing_config_map.get(item.key)
            config_model = PluginConfigManager.build_config_model(manifest.id, item)
            if existing_config:
                migrated_config_value = PluginConfigManager.migrate_config_secret_storage(existing_config, item)
                await PluginDao.update_plugin_config(
                    query_db,
                    {
                        'plugin_id': manifest.id,
                        'config_key': item.key,
                        'config_label': config_model.config_label,
                        'config_type': config_model.config_type,
                        'config_value': migrated_config_value,
                        'default_value': config_model.default_value,
                        'required': config_model.required,
                        'secret': config_model.secret,
                        'options': config_model.options,
                        'description': config_model.description,
                        'update_time': datetime.now(),
                    },
                )
            else:
                await PluginDao.add_plugin_config(query_db, config_model)
            installed_configs.append(config_model)

        await PluginDao.delete_plugin_configs_except(query_db, manifest.id, desired_config_keys)
        return installed_configs

    @classmethod
    async def install_plugin_job_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        enabled: bool,
    ) -> None:
        """
        将单个插件的任务资源同步到 manifest 期望状态。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param enabled: 插件任务是否允许启用
        :return: None
        """
        await PluginJobInstaller(query_db).install_plugin_jobs(discovered_plugin, enabled=enabled)

    @classmethod
    async def get_plugin_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        reveal_secret: bool = False,
    ) -> list[PluginConfigValueModel]:
        """
        获取插件配置列表。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置值列表
        """
        config_list = await PluginDao.get_plugin_config_list(query_db, discovered_plugin.manifest.id)
        config_map = {config.config_key: config for config in config_list}

        return [
            PluginConfigManager.build_config_value(
                config_map.get(item.key) or PluginConfigManager.build_config_model(discovered_plugin.manifest.id, item),
                item,
                reveal_secret=reveal_secret,
            )
            for item in discovered_plugin.manifest.config.items
        ]

    @classmethod
    async def is_plugin_installed_services(cls, query_db: AsyncSession, plugin_id: str) -> bool:
        """
        判断插件是否已经完成安装。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 是否已安装
        """
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        return bool(plugin and plugin.installed_version)

    @classmethod
    async def update_plugin_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        update_model: PluginConfigUpdateModel,
    ) -> list[PluginConfigValueModel]:
        """
        更新插件配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param update_model: 插件配置更新模型
        :return: 更新后的插件配置值列表
        """
        await cls.install_plugin_default_config_services(query_db, discovered_plugin)
        manifest_items = {item.key: item for item in discovered_plugin.manifest.config.items}
        for key, value in update_model.values.items():
            item = manifest_items.get(key)
            if not item:
                raise ValueError(f'插件未声明配置：{key}')
            if item.secret and value == PluginConfigManager.MASK_VALUE:
                continue
            PluginConfigManager.validate_update_value(item, value)
            await PluginDao.update_plugin_config(
                query_db,
                {
                    'plugin_id': discovered_plugin.manifest.id,
                    'config_key': key,
                    'config_value': PluginConfigManager.serialize_config_value(value, secret=item.secret),
                    'update_time': datetime.now(),
                },
            )

        return await cls.get_plugin_config_services(query_db, discovered_plugin)

    @classmethod
    async def add_plugin_operation_log_services(
        cls,
        query_db: AsyncSession,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> PluginOperationLogModel:
        """
        记录插件批量操作审计日志。

        :param query_db: orm对象
        :param payload: 插件批量执行结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量操作审计日志模型
        """
        operation_log = PluginOperationLogBuilder.build_model(
            payload,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )
        db_operation_log = await PluginDao.add_plugin_operation_log(query_db, operation_log)

        return PluginOperationLogModel(**CamelCaseUtil.transform_result(db_operation_log))

    @classmethod
    async def get_plugin_operation_log_page_list_services(
        cls,
        query_db: AsyncSession,
        query_object: PluginOperationLogPageQueryModel,
        is_page: bool = True,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取插件批量操作审计日志分页列表。

        :param query_db: orm对象
        :param query_object: 插件批量操作审计日志分页查询对象
        :param is_page: 是否开启分页
        :return: 插件批量操作审计日志分页列表或列表
        """
        page_result = await PluginDao.get_plugin_operation_log_page_list(query_db, query_object, is_page)
        if not isinstance(page_result, PageModel):
            return page_result

        page_result.rows = [PluginOperationLogBuilder.build_detail(row) for row in page_result.rows]

        return page_result

    @classmethod
    async def get_plugin_operation_log_export_list_services(
        cls,
        query_db: AsyncSession,
        query_object: PluginOperationLogExportQueryModel,
    ) -> list[PluginOperationLogDetailModel]:
        """
        获取插件批量操作审计日志导出列表。

        :param query_db: orm对象
        :param query_object: 插件批量操作审计日志导出查询对象
        :return: 插件批量操作审计日志导出详情列表
        """
        operation_log_list = await PluginDao.get_plugin_operation_log_export_list(query_db, query_object)

        return [PluginOperationLogBuilder.build_detail(operation_log) for operation_log in operation_log_list]

    @classmethod
    def export_plugin_operation_log_list_services(
        cls,
        operation_log_list: list[PluginOperationLogDetailModel],
        operation_dict: dict[str, str] | None = None,
    ) -> bytes:
        """
        导出插件批量操作审计日志。

        :param operation_log_list: 插件批量操作审计日志导出详情列表
        :param operation_dict: 插件操作类型字典
        :return: 插件批量操作审计日志 Excel 二进制数据
        """
        export_list = [
            PluginOperationLogBuilder.build_export_row(operation_log, operation_dict)
            for operation_log in operation_log_list
        ]
        mapping_dict = {
            'operationId': '日志编号',
            'operation': '操作类型',
            'pluginIds': '目标插件',
            'dryRun': '是否预演',
            'continueOnError': '失败后继续',
            'status': '执行状态',
            'summary': '执行汇总',
            'remark': '备注',
            'createTime': '创建时间',
        }

        return ExcelUtil.export_list2excel(export_list, mapping_dict)

    @classmethod
    async def retain_plugin_operation_log_services(
        cls,
        query_db: AsyncSession,
        retention_model: PluginOperationLogRetentionModel,
    ) -> PluginOperationLogRetentionResultModel:
        """
        按保留策略清理插件批量操作审计日志。

        :param query_db: orm对象
        :param retention_model: 插件批量操作审计日志保留策略模型
        :return: 插件批量操作审计日志保留策略执行结果
        """
        cutoff_time = datetime.now() - timedelta(days=retention_model.retention_days)
        matched_count = await PluginDao.count_plugin_operation_logs_before(query_db, cutoff_time)
        deleted_count = 0
        if not retention_model.dry_run:
            deleted_count = await PluginDao.delete_plugin_operation_logs_before(query_db, cutoff_time)

        return PluginOperationLogRetentionResultModel(
            retentionDays=retention_model.retention_days,
            cutoffTime=cutoff_time,
            matchedCount=matched_count,
            deletedCount=deleted_count,
            dryRun=retention_model.dry_run,
        )

    @classmethod
    async def plugin_operation_log_detail_services(
        cls,
        query_db: AsyncSession,
        operation_id: int,
    ) -> PluginOperationLogDetailModel | None:
        """
        获取插件批量操作审计日志详情。

        :param query_db: orm对象
        :param operation_id: 操作日志ID
        :return: 插件批量操作审计日志详情
        """
        operation_log = await PluginDao.get_plugin_operation_log_by_id(query_db, operation_id)
        if not operation_log:
            return None

        return PluginOperationLogBuilder.build_detail(CamelCaseUtil.transform_result(operation_log))

    @classmethod
    async def check_installed_menu_conflict_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> list[PluginMenuConflictItem]:
        """
        检查目标插件与数据库已存在菜单的权限冲突。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 菜单冲突检查项列表
        """
        conflicts = []
        for menu in PluginMenuTree.flatten(discovered_plugin.manifest.frontend.menus):
            if not menu.perms:
                continue
            sys_menu = await PluginDao.get_sys_menu_by_perms(query_db, menu.perms)
            if not sys_menu:
                continue
            plugin_menu = await PluginDao.get_plugin_menu_by_menu_id(query_db, sys_menu.menu_id)
            conflict_plugin_id = plugin_menu.plugin_id if plugin_menu else None
            if conflict_plugin_id == discovered_plugin.manifest.id:
                continue
            conflict_label = conflict_plugin_id or 'core'
            conflicts.append(
                PluginMenuConflictItem(
                    kind='installed_permission',
                    plugin_id=discovered_plugin.manifest.id,
                    conflict_plugin_id=conflict_plugin_id,
                    value=menu.perms,
                    message=(
                        f'插件 {discovered_plugin.manifest.id} 权限 {menu.perms} '
                        f'与已存在菜单 {sys_menu.menu_id}（{conflict_label}）冲突'
                    ),
                )
            )

        return conflicts

    @classmethod
    async def mark_plugin_error_services(
        cls, query_db: AsyncSession, plugin_id: str, error_message: str
    ) -> CrudResponseModel:
        """
        标记插件错误。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 操作响应
        """
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        if not plugin:
            return CrudResponseModel(is_success=False, message='插件不存在')

        await PluginDao.update_plugin(
            query_db,
            {
                'plugin_id': plugin_id,
                'status': PluginStateTransitionTable.resolve_target(getattr(plugin, 'status', None), 'mark_error')
                or 'error',
                'last_error': error_message[:1000],
                'update_time': datetime.now(),
            },
        )
        await PluginMenuInstaller(query_db).set_plugin_menu_status(plugin_id, '1')
        await PluginJobInstaller(query_db).pause_plugin_jobs(plugin_id)

        return CrudResponseModel(is_success=True, message='插件状态已标记为异常')

    @classmethod
    async def recover_plugin_dependency_error_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> CrudResponseModel:
        """
        在启动依赖重新满足后恢复插件状态。

        仅恢复由启动依赖检查写入的 error。恢复目标由已安装版本和当前源码版本
        重新推导，未安装插件回到 discovered，已安装插件回到 installed 或
        pending_upgrade；同时恢复启动前的启用意图并清除历史依赖错误。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 操作响应
        """
        plugin_id = discovered_plugin.manifest.id
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        if not plugin:
            return CrudResponseModel(is_success=False, message='插件不存在')

        last_error = getattr(plugin, 'last_error', None)
        if (
            getattr(plugin, 'status', None) != 'error'
            or not isinstance(last_error, str)
            or not last_error.startswith(PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX)
        ):
            return CrudResponseModel(is_success=False, message='插件不是启动依赖检查异常状态')

        installed_version = getattr(plugin, 'installed_version', None)
        desired_enabled = PluginStateResolver.db_value_to_enabled(
            getattr(plugin, 'enabled', None),
            fallback=False,
        )
        target_status = PluginStateResolver.resolve(
            PluginStateSnapshot(
                source_version=discovered_plugin.manifest.version,
                installed_version=installed_version,
                enabled=desired_enabled,
                current_status=None,
            )
        )
        await PluginDao.update_plugin(
            query_db,
            {
                'plugin_id': plugin_id,
                'status': target_status,
                'last_error': None,
                'update_time': datetime.now(),
            },
        )

        return CrudResponseModel(is_success=True, message=f'插件启动依赖已恢复，状态：{target_status}')

    @classmethod
    async def build_plugin_purge_plan_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginPurgePlan:
        """
        构建插件物理清理计划。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件物理清理计划
        """
        plugin_id = discovered_plugin.manifest.id
        menu_count = await PluginDao.count_plugin_menus(query_db, plugin_id)
        config_count = await PluginDao.count_plugin_configs(query_db, plugin_id)
        migration_count = await PluginDao.count_plugin_migrations(query_db, plugin_id)
        job_count = await PluginJobRepository(query_db).count_jobs_by_name_prefix(f'{plugin_id}:')

        return PluginPurgePlanner.build_plan(
            discovered_plugin,
            menu_count=menu_count,
            config_count=config_count,
            migration_count=migration_count,
            job_count=job_count,
        )

    @classmethod
    async def purge_plugin_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginPurgePlan:
        """
        清理插件平台元数据。

        该方法只清理由平台拥有的插件记录、菜单关联、配置、migration 历史和插件任务；
        插件业务数据需由运行时在调用本方法前通过 on_purge 钩子显式清理。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 执行前构建的插件物理清理计划
        """
        plugin_id = discovered_plugin.manifest.id
        plan = await cls.build_plugin_purge_plan_services(query_db, discovered_plugin)
        await cls._purge_plugin_metadata_by_id(query_db, plugin_id)

        return plan

    @classmethod
    async def build_plugin_purge_plan_by_id_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
    ) -> PluginPurgePlan:
        """
        为源码已缺失的插件按 ID 构建平台元数据清理计划。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 插件物理清理计划
        """
        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        menu_count = await PluginDao.count_plugin_menus(query_db, plugin_id)
        config_count = await PluginDao.count_plugin_configs(query_db, plugin_id)
        migration_count = await PluginDao.count_plugin_migrations(query_db, plugin_id)
        job_count = await PluginJobRepository(query_db).count_jobs_by_name_prefix(f'{plugin_id}:')

        return PluginPurgePlanner.build_metadata_plan(
            plugin_id,
            state_count=1 if plugin else 0,
            menu_count=menu_count,
            config_count=config_count,
            migration_count=migration_count,
            job_count=job_count,
        )

    @classmethod
    async def purge_plugin_metadata_by_id_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
    ) -> PluginPurgePlan:
        """
        按插件 ID 清理平台拥有的孤儿元数据。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 执行前构建的插件物理清理计划
        """
        plan = await cls.build_plugin_purge_plan_by_id_services(query_db, plugin_id)
        await cls._purge_plugin_metadata_by_id(query_db, plugin_id)

        return plan

    @classmethod
    async def _purge_plugin_metadata_by_id(cls, query_db: AsyncSession, plugin_id: str) -> None:
        """
        删除平台能够按插件 ID 确认归属的元数据。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: None
        """
        plugin_menus = await PluginDao.get_plugin_menu_list(query_db, plugin_id)
        menu_ids = [plugin_menu.menu_id for plugin_menu in plugin_menus]

        plugin = await PluginDao.get_plugin_by_id(query_db, plugin_id)
        if plugin:
            await cls.update_plugin_enabled_services(query_db, plugin_id, enabled=False)
        await PluginDao.delete_plugin_menus(query_db, plugin_id)
        await PluginDao.delete_sys_menus_by_ids(query_db, menu_ids)
        await PluginDao.delete_plugin_configs(query_db, plugin_id)
        await PluginDao.delete_plugin_migrations(query_db, plugin_id)
        await PluginJobRepository(query_db).delete_jobs_by_name_prefix(f'{plugin_id}:')
        await PluginDao.delete_plugin(query_db, plugin_id)

    @classmethod
    async def upsert_plugin_menu_services(
        cls, query_db: AsyncSession, plugin_id: str, menu_id: int, menu_key: str
    ) -> PluginMenuModel:
        """
        写入插件菜单关联。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param menu_id: 菜单ID
        :param menu_key: 插件内菜单自然键
        :return: 插件菜单关联对象
        """
        existing_plugin_menu = await PluginDao.get_plugin_menu_by_key(query_db, plugin_id, menu_key)
        plugin_menu_model = PluginMenuModel(pluginId=plugin_id, menuId=menu_id, menuKey=menu_key)

        if existing_plugin_menu and existing_plugin_menu.menu_id != menu_id:
            await PluginDao.update_plugin_menu_by_key(query_db, plugin_menu_model)
        elif not existing_plugin_menu:
            await PluginDao.add_plugin_menu(query_db, plugin_menu_model)

        return plugin_menu_model

    @classmethod
    async def get_plugin_migration_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationModel | None:
        """
        获取插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 执行历史对象
        """
        plugin_migration = await PluginDao.get_plugin_migration_by_path(query_db, plugin_id, migration_path)
        if not plugin_migration:
            return None

        return PluginMigrationModel(**CamelCaseUtil.transform_result(plugin_migration))

    @classmethod
    async def get_plugin_migration_list_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        status: str | None = None,
    ) -> list[PluginMigrationModel]:
        """
        获取插件 migration 执行历史列表。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 执行历史列表
        """
        plugin_migrations = await PluginDao.get_plugin_migration_list(query_db, plugin_id, status)

        return [PluginMigrationModel(**CamelCaseUtil.transform_result(item)) for item in plugin_migrations]

    @classmethod
    async def add_plugin_migration_services(
        cls,
        query_db: AsyncSession,
        plugin_migration: PluginMigrationModel,
    ) -> PluginMigrationModel:
        """
        新增插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_migration: 插件 migration 执行历史对象
        :return: 插件 migration 执行历史对象
        """
        await PluginDao.add_plugin_migration(query_db, plugin_migration)

        return plugin_migration

    @classmethod
    async def mark_plugin_migration_status_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> PluginMigrationModel | None:
        """
        人工标记插件 migration 执行历史状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 更新后的插件 migration 执行历史对象
        """
        plugin_migration = await PluginDao.update_plugin_migration_status(
            query_db,
            plugin_id,
            migration_path,
            status,
            error_message,
        )
        if not plugin_migration:
            return None

        return PluginMigrationModel(**CamelCaseUtil.transform_result(plugin_migration))

    @staticmethod
    def _build_plugin_model(
        discovered_plugin: DiscoveredPlugin,
        backend_root: Path,
        frontend_root: Path | None,
        existing_plugin: object | None,
    ) -> PluginModel:
        """
        根据发现结果和数据库状态构建插件信息模型。

        :param discovered_plugin: 已发现插件对象
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :param existing_plugin: 数据库中已有插件对象
        :return: 插件信息模型
        """
        manifest = discovered_plugin.manifest
        capability = PluginRuntimeCapabilityResolver(
            frontend_mode=PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_mode(),
            backend_runtime_mode=PLUGIN_RUNTIME_ENVIRONMENT.get_backend_runtime_mode(),
        ).resolve(discovered_plugin)
        current_enabled = getattr(existing_plugin, 'enabled', None)
        enabled = current_enabled if current_enabled is not None else '0'
        installed_version = getattr(existing_plugin, 'installed_version', None)
        current_status = getattr(existing_plugin, 'status', None)
        last_error = getattr(existing_plugin, 'last_error', None)
        status = PluginService._resolve_status(manifest.version, installed_version, enabled, current_status)
        frontend_path = frontend_root / manifest.frontend.plugin_id if frontend_root else None
        frontend_menus = PluginMenuTree.flatten(manifest.frontend.menus)

        return PluginModel(
            pluginId=manifest.id,
            pluginName=manifest.name,
            version=manifest.version,
            installedVersion=installed_version,
            enabled=enabled,
            status=status,
            source='local',
            backendPath=str(discovered_plugin.backend_path.relative_to(backend_root)),
            frontendPath=str(frontend_path.relative_to(frontend_root)) if frontend_path and frontend_root else None,
            lastError=last_error,
            description=manifest.description,
            updateTime=datetime.now(),
            capability=capability.to_payload(),
            metadata=manifest.metadata.model_dump(by_alias=True),
            backend={
                'module': manifest.backend.module,
                'autoScanRouters': manifest.backend.routers.auto_scan,
                'migrations': manifest.backend.migrations,
                'seeds': manifest.backend.seeds,
                'jobs': [job.model_dump(by_alias=True) for job in manifest.backend.jobs],
            },
            frontend={
                'pluginId': manifest.frontend.plugin_id,
                'basePath': manifest.frontend.base_path,
                'viewsPath': manifest.frontend.views_path,
                'apiPath': manifest.frontend.api_path,
                'delivery': manifest.frontend.delivery.model_dump(by_alias=True),
                'menus': [menu.model_dump(by_alias=True) for menu in frontend_menus],
            },
            permissions=[permission.model_dump(by_alias=True) for permission in manifest.permissions],
            config=[config_item.model_dump(by_alias=True) for config_item in manifest.config.items],
            dependencies={
                'python': manifest.dependencies.python,
                'npm': manifest.dependencies.npm,
                'npmDev': manifest.dependencies.npm_dev,
            },
            pluginDependencies=[dependency.model_dump(by_alias=True) for dependency in manifest.dependencies.plugins],
        )

    @classmethod
    def _build_orphan_plugin_model(cls, plugin: object) -> PluginModel:
        """
        构建源码缺失但平台元数据仍存在的孤儿插件视图。

        孤儿记录只能执行平台元数据物理清理，其他生命周期操作均依赖缺失的
        manifest 和源码，因此通过 capability 明确阻断。

        :param plugin: 数据库插件状态对象
        :return: 孤儿插件信息模型
        """
        model = PluginModel(**CamelCaseUtil.transform_result(plugin))
        blocked_operations = sorted(STATE_CHANGE_OPERATIONS - {'purge'})
        return model.model_copy(
            update={
                'source': 'orphan',
                'capability': {
                    'pluginId': model.plugin_id,
                    'frontendMode': PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_mode(),
                    'backendRuntimeMode': PLUGIN_RUNTIME_ENVIRONMENT.get_backend_runtime_mode(),
                    'hasFrontendResources': False,
                    'frontendBuildRequired': False,
                    'frontendRuntimeManageable': False,
                    'backendRuntimeManageable': False,
                    'runtimeManageable': False,
                    'blockedOperations': blocked_operations,
                    'warnings': [cls.ORPHAN_PLUGIN_REASON],
                    'primaryReason': cls.ORPHAN_PLUGIN_REASON,
                },
            }
        )

    @staticmethod
    def _resolve_status(
        version: str,
        installed_version: str | None,
        enabled: str,
        current_status: str | None = None,
    ) -> PluginStatus:
        """
        解析插件状态。

        :param version: 当前源码版本
        :param installed_version: 已安装版本
        :param enabled: 启停状态
        :param current_status: 当前数据库状态
        :return: 插件状态
        """
        return PluginStateResolver.resolve(
            PluginStateSnapshot(
                source_version=version,
                installed_version=installed_version,
                enabled=PluginStateResolver.db_value_to_enabled(enabled, fallback=False),
                current_status=current_status,
            )
        )

    @staticmethod
    def _filter_plugin_page_items(
        plugin_items: list[dict[str, Any]],
        query_object: PluginPageQueryModel,
    ) -> list[dict[str, Any]]:
        """
        根据插件管理页面查询条件过滤插件列表。

        :param plugin_items: 插件列表项
        :param query_object: 插件分页查询对象
        :return: 过滤后的插件列表项
        """

        def contains(value: object, keyword: str | None) -> bool:
            return keyword is None or keyword in str(value or '')

        return [
            item
            for item in plugin_items
            if contains(item.get('pluginId'), query_object.plugin_id)
            and contains(item.get('pluginName'), query_object.plugin_name)
            and (query_object.enabled is None or item.get('enabled') == query_object.enabled)
            and (query_object.status is None or item.get('status') == query_object.status)
            and (query_object.source is None or item.get('source') == query_object.source)
        ]

    @staticmethod
    def _get_discovered_plugin(backend_root: Path, plugin_id: str) -> DiscoveredPlugin | None:
        """
        从本地插件目录获取指定插件发现结果。

        :param backend_root: 后端插件根目录
        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        for discovered_plugin in PluginScanner(backend_root).discover():
            if discovered_plugin.manifest.id == plugin_id:
                return discovered_plugin

        return None
