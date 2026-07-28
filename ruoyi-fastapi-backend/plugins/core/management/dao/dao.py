from collections.abc import Sequence
from datetime import datetime, time
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.role_do import SysRoleMenu
from module_admin.entity.vo.menu_vo import MenuModel
from plugins.core.management.entity.do.models import (
    SysPlugin,
    SysPluginConfig,
    SysPluginMenu,
    SysPluginMigration,
    SysPluginOperationLog,
)
from plugins.core.management.entity.vo.schemas import (
    PluginConfigModel,
    PluginMenuModel,
    PluginMigrationModel,
    PluginModel,
    PluginOperationLogExportQueryModel,
    PluginOperationLogModel,
    PluginOperationLogPageQueryModel,
    PluginPageQueryModel,
)
from plugins.core.utils import escape_sql_like
from utils.page_util import PageUtil

PLUGIN_MODEL_RUNTIME_FIELDS = {
    'capability',
    'metadata',
    'backend',
    'frontend',
    'permissions',
    'config',
    'dependencies',
    'plugin_dependencies',
}


class PluginDao:
    """
    插件系统数据库操作层。
    """

    @classmethod
    async def get_plugin_by_id(cls, db: AsyncSession, plugin_id: str) -> SysPlugin | None:
        """
        根据插件 ID 查询插件。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件信息对象
        """
        plugin = (await db.execute(select(SysPlugin).where(SysPlugin.plugin_id == plugin_id))).scalars().first()

        return plugin

    @classmethod
    async def get_plugin_list(cls, db: AsyncSession) -> Sequence[SysPlugin]:
        """
        查询插件列表。

        :param db: orm对象
        :return: 插件信息列表
        """
        plugin_list = (await db.execute(select(SysPlugin).order_by(SysPlugin.plugin_id))).scalars().all()

        return plugin_list

    @classmethod
    async def get_plugin_page_list(
        cls,
        db: AsyncSession,
        query_object: PluginPageQueryModel,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取插件列表。

        :param db: orm对象
        :param query_object: 插件查询对象
        :param is_page: 是否开启分页
        :return: 插件列表分页对象或插件列表
        """
        query = (
            select(SysPlugin)
            .where(
                SysPlugin.plugin_id.like(f'%{query_object.plugin_id}%') if query_object.plugin_id else True,
                SysPlugin.plugin_name.like(f'%{query_object.plugin_name}%') if query_object.plugin_name else True,
                SysPlugin.enabled == query_object.enabled if query_object.enabled else True,
                SysPlugin.status == query_object.status if query_object.status else True,
                SysPlugin.source == query_object.source if query_object.source else True,
            )
            .order_by(SysPlugin.plugin_id)
            .distinct()
        )
        plugin_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db,
            query,
            query_object.page_num,
            query_object.page_size,
            is_page,
        )

        return plugin_list

    @classmethod
    async def add_plugin(cls, db: AsyncSession, plugin: PluginModel) -> SysPlugin:
        """
        新增插件。

        :param db: orm对象
        :param plugin: 插件信息对象
        :return: 新增后的插件信息对象
        """
        db_plugin = SysPlugin(**cls.dump_plugin_persistence_payload(plugin))
        db.add(db_plugin)
        await db.flush()

        return db_plugin

    @staticmethod
    def dump_plugin_persistence_payload(plugin: PluginModel) -> dict[str, Any]:
        """
        序列化插件数据库持久化字段。

        :param plugin: 插件信息对象
        :return: 可写入 sys_plugin 的字段字典
        """
        return plugin.model_dump(exclude_unset=True, exclude=PLUGIN_MODEL_RUNTIME_FIELDS)

    @classmethod
    async def update_plugin(cls, db: AsyncSession, plugin: dict) -> None:
        """
        更新插件。

        :param db: orm对象
        :param plugin: 插件更新字典
        :return: None
        """
        await db.execute(update(SysPlugin), [plugin])

    @classmethod
    async def delete_plugin(cls, db: AsyncSession, plugin_id: str) -> None:
        """
        删除插件记录。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: None
        """
        await db.execute(delete(SysPlugin).where(SysPlugin.plugin_id == plugin_id))

    @classmethod
    async def count_plugin_menus(cls, db: AsyncSession, plugin_id: str) -> int:
        """
        统计插件菜单关联数量。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件菜单关联数量
        """
        matched_count = (
            await db.execute(
                select(func.count()).select_from(SysPluginMenu).where(SysPluginMenu.plugin_id == plugin_id)
            )
        ).scalar_one()

        return int(matched_count)

    @classmethod
    async def get_plugin_menu_list(cls, db: AsyncSession, plugin_id: str) -> Sequence[SysPluginMenu]:
        """
        查询插件菜单关联列表。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件菜单关联列表
        """
        plugin_menu_list = (
            (await db.execute(select(SysPluginMenu).where(SysPluginMenu.plugin_id == plugin_id))).scalars().all()
        )

        return plugin_menu_list

    @classmethod
    async def get_plugin_menu_by_key(cls, db: AsyncSession, plugin_id: str, menu_key: str) -> SysPluginMenu | None:
        """
        根据插件菜单自然键查询菜单关联。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param menu_key: 插件内菜单自然键
        :return: 插件菜单关联对象
        """
        plugin_menu = (
            (
                await db.execute(
                    select(SysPluginMenu).where(
                        SysPluginMenu.plugin_id == plugin_id,
                        SysPluginMenu.menu_key == menu_key,
                    )
                )
            )
            .scalars()
            .first()
        )

        return plugin_menu

    @classmethod
    async def add_plugin_menu(cls, db: AsyncSession, plugin_menu: PluginMenuModel) -> SysPluginMenu:
        """
        新增插件菜单关联。

        :param db: orm对象
        :param plugin_menu: 插件菜单关联对象
        :return: 新增后的插件菜单关联对象
        """
        db_plugin_menu = SysPluginMenu(**plugin_menu.model_dump(exclude_unset=True))
        db.add(db_plugin_menu)
        await db.flush()

        return db_plugin_menu

    @classmethod
    async def update_plugin_menu_by_key(cls, db: AsyncSession, plugin_menu: PluginMenuModel) -> None:
        """
        根据插件菜单自然键更新插件菜单关联。

        :param db: orm对象
        :param plugin_menu: 插件菜单关联对象
        :return: None
        """
        await db.execute(
            update(SysPluginMenu)
            .where(SysPluginMenu.plugin_id == plugin_menu.plugin_id, SysPluginMenu.menu_key == plugin_menu.menu_key)
            .values(menu_id=plugin_menu.menu_id)
        )

    @classmethod
    async def update_plugin_menu_key_by_menu_id(cls, db: AsyncSession, plugin_menu: PluginMenuModel) -> None:
        """
        根据菜单 ID 更新当前插件的菜单自然键。

        :param db: orm对象
        :param plugin_menu: 插件菜单关联对象
        :return: None
        """
        await db.execute(
            update(SysPluginMenu)
            .where(
                SysPluginMenu.plugin_id == plugin_menu.plugin_id,
                SysPluginMenu.menu_id == plugin_menu.menu_id,
            )
            .values(menu_key=plugin_menu.menu_key)
        )

    @classmethod
    async def delete_plugin_menus(cls, db: AsyncSession, plugin_id: str) -> None:
        """
        删除插件菜单关联。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: None
        """
        await db.execute(delete(SysPluginMenu).where(SysPluginMenu.plugin_id == plugin_id))

    @classmethod
    async def delete_plugin_menus_by_ids(cls, db: AsyncSession, plugin_id: str, menu_ids: list[int]) -> None:
        """
        根据菜单 ID 删除指定插件的菜单 ownership 关联。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param menu_ids: 菜单ID列表
        :return: None
        """
        if menu_ids:
            await db.execute(
                delete(SysPluginMenu).where(
                    SysPluginMenu.plugin_id == plugin_id,
                    SysPluginMenu.menu_id.in_(menu_ids),
                )
            )

    @classmethod
    async def delete_sys_menus_by_ids(cls, db: AsyncSession, menu_ids: list[int]) -> None:
        """
        根据菜单 ID 删除系统菜单及角色菜单关联。

        :param db: orm对象
        :param menu_ids: 菜单ID列表
        :return: None
        """
        if menu_ids:
            await db.execute(delete(SysRoleMenu).where(SysRoleMenu.menu_id.in_(menu_ids)))
            await db.execute(delete(SysMenu).where(SysMenu.menu_id.in_(menu_ids)))

    @classmethod
    async def count_plugin_migrations(cls, db: AsyncSession, plugin_id: str) -> int:
        """
        统计插件 migration 历史数量。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: migration 历史数量
        """
        matched_count = (
            await db.execute(
                select(func.count()).select_from(SysPluginMigration).where(SysPluginMigration.plugin_id == plugin_id)
            )
        ).scalar_one()

        return int(matched_count)

    @classmethod
    async def delete_plugin_migrations(cls, db: AsyncSession, plugin_id: str) -> None:
        """
        删除插件 migration 历史。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: None
        """
        await db.execute(delete(SysPluginMigration).where(SysPluginMigration.plugin_id == plugin_id))

    @classmethod
    async def get_plugin_migration_by_path(
        cls,
        db: AsyncSession,
        plugin_id: str,
        migration_path: str,
    ) -> SysPluginMigration | None:
        """
        根据插件 ID 和 migration 路径查询执行历史。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: migration 执行历史对象
        """
        plugin_migration = (
            (
                await db.execute(
                    select(SysPluginMigration).where(
                        SysPluginMigration.plugin_id == plugin_id,
                        SysPluginMigration.migration_path == migration_path,
                    )
                )
            )
            .scalars()
            .first()
        )

        return plugin_migration

    @classmethod
    async def get_plugin_migration_list(
        cls,
        db: AsyncSession,
        plugin_id: str,
        status: str | None = None,
    ) -> Sequence[SysPluginMigration]:
        """
        查询插件 migration 历史列表。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: migration 执行历史列表
        """
        migration_list = (
            (
                await db.execute(
                    select(SysPluginMigration)
                    .where(
                        SysPluginMigration.plugin_id == plugin_id,
                        SysPluginMigration.status == status if status else True,
                    )
                    .order_by(SysPluginMigration.migration_path)
                )
            )
            .scalars()
            .all()
        )

        return migration_list

    @classmethod
    async def update_plugin_migration_status(
        cls,
        db: AsyncSession,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None,
    ) -> SysPluginMigration | None:
        """
        更新插件 migration 执行历史状态。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 更新后的 migration 执行历史对象
        """
        existing_plugin_migration = await cls.get_plugin_migration_by_path(db, plugin_id, migration_path)
        if not existing_plugin_migration:
            return None

        now = datetime.now()
        await db.execute(
            update(SysPluginMigration)
            .where(
                SysPluginMigration.plugin_id == plugin_id,
                SysPluginMigration.migration_path == migration_path,
            )
            .values(status=status, error_message=error_message, finished_time=now, update_time=now)
        )
        await db.flush()

        return await cls.get_plugin_migration_by_path(db, plugin_id, migration_path)

    @classmethod
    async def add_plugin_migration(
        cls,
        db: AsyncSession,
        plugin_migration: PluginMigrationModel,
    ) -> SysPluginMigration:
        """
        新增插件 migration 执行历史。

        :param db: orm对象
        :param plugin_migration: 插件 migration 执行历史对象
        :return: 新增后的 migration 执行历史对象
        """
        payload = plugin_migration.model_dump(exclude_unset=True)
        now = datetime.now()
        cls._apply_migration_observability_payload(payload, None, now)
        if payload.get('status') == 'success' and 'error_message' not in payload:
            payload['error_message'] = None
        existing_plugin_migration = await cls.get_plugin_migration_by_path(
            db,
            plugin_migration.plugin_id,
            plugin_migration.migration_path,
        )
        if existing_plugin_migration:
            cls._apply_migration_observability_payload(payload, existing_plugin_migration, now)
            await db.execute(
                update(SysPluginMigration)
                .where(
                    SysPluginMigration.plugin_id == plugin_migration.plugin_id,
                    SysPluginMigration.migration_path == plugin_migration.migration_path,
                )
                .values(**payload)
            )
            await db.flush()
            return existing_plugin_migration

        db_plugin_migration = SysPluginMigration(**payload)
        db.add(db_plugin_migration)
        await db.flush()

        return db_plugin_migration

    @staticmethod
    def _apply_migration_observability_payload(
        payload: dict[str, Any],
        existing_plugin_migration: SysPluginMigration | None,
        now: datetime,
    ) -> None:
        """
        补充 migration 状态观测字段。

        :param payload: 待写入 payload
        :param existing_plugin_migration: 已有 migration 历史
        :param now: 当前时间
        :return: None
        """
        status = payload.get('status', 'success')
        payload.setdefault('update_time', now)
        if status == 'running':
            payload.setdefault('started_time', now)
            payload.setdefault('finished_time', None)
            payload['attempt_count'] = int(getattr(existing_plugin_migration, 'attempt_count', 0) or 0) + 1
            return

        if status in {'success', 'failed'}:
            payload.setdefault('finished_time', now)

    @classmethod
    async def get_plugin_config_list(cls, db: AsyncSession, plugin_id: str) -> Sequence[SysPluginConfig]:
        """
        查询插件配置列表。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件配置列表
        """
        plugin_config_list = (
            (await db.execute(select(SysPluginConfig).where(SysPluginConfig.plugin_id == plugin_id))).scalars().all()
        )

        return plugin_config_list

    @classmethod
    async def count_plugin_configs(cls, db: AsyncSession, plugin_id: str) -> int:
        """
        统计插件配置数量。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件配置数量
        """
        matched_count = (
            await db.execute(
                select(func.count()).select_from(SysPluginConfig).where(SysPluginConfig.plugin_id == plugin_id)
            )
        ).scalar_one()

        return int(matched_count)

    @classmethod
    async def delete_plugin_configs(cls, db: AsyncSession, plugin_id: str) -> None:
        """
        删除插件配置。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: None
        """
        await db.execute(delete(SysPluginConfig).where(SysPluginConfig.plugin_id == plugin_id))

    @classmethod
    async def delete_plugin_configs_except(cls, db: AsyncSession, plugin_id: str, config_keys: set[str]) -> None:
        """
        删除不再由 manifest 声明的插件配置。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param config_keys: 当前 manifest 配置键集合
        :return: None
        """
        query = delete(SysPluginConfig).where(SysPluginConfig.plugin_id == plugin_id)
        if config_keys:
            query = query.where(SysPluginConfig.config_key.not_in(sorted(config_keys)))
        await db.execute(query)

    @classmethod
    async def get_plugin_config_by_key(
        cls,
        db: AsyncSession,
        plugin_id: str,
        config_key: str,
    ) -> SysPluginConfig | None:
        """
        根据插件 ID 和配置键名查询插件配置。

        :param db: orm对象
        :param plugin_id: 插件ID
        :param config_key: 配置键名
        :return: 插件配置对象
        """
        plugin_config = (
            (
                await db.execute(
                    select(SysPluginConfig).where(
                        SysPluginConfig.plugin_id == plugin_id,
                        SysPluginConfig.config_key == config_key,
                    )
                )
            )
            .scalars()
            .first()
        )

        return plugin_config

    @classmethod
    async def add_plugin_config(cls, db: AsyncSession, plugin_config: PluginConfigModel) -> SysPluginConfig:
        """
        新增插件配置。

        :param db: orm对象
        :param plugin_config: 插件配置对象
        :return: 新增后的插件配置对象
        """
        db_plugin_config = SysPluginConfig(**plugin_config.model_dump(exclude_unset=True))
        db.add(db_plugin_config)
        await db.flush()

        return db_plugin_config

    @classmethod
    async def update_plugin_config(cls, db: AsyncSession, plugin_config: dict) -> None:
        """
        更新插件配置。

        :param db: orm对象
        :param plugin_config: 插件配置更新字典
        :return: None
        """
        await db.execute(update(SysPluginConfig), [plugin_config])

    @classmethod
    async def add_plugin_operation_log(
        cls,
        db: AsyncSession,
        operation_log: PluginOperationLogModel,
    ) -> SysPluginOperationLog:
        """
        新增插件批量操作审计日志。

        :param db: orm对象
        :param operation_log: 插件批量操作审计日志对象
        :return: 新增后的插件批量操作审计日志对象
        """
        db_operation_log = SysPluginOperationLog(**operation_log.model_dump(exclude_unset=True))
        db.add(db_operation_log)
        await db.flush()

        return db_operation_log

    @classmethod
    async def get_plugin_operation_log_page_list(
        cls,
        db: AsyncSession,
        query_object: PluginOperationLogPageQueryModel,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取插件批量操作审计日志列表。

        :param db: orm对象
        :param query_object: 插件批量操作审计日志查询对象
        :param is_page: 是否开启分页
        :return: 插件批量操作审计日志分页对象或列表
        """
        query = (
            cls._build_operation_log_query(query_object).order_by(SysPluginOperationLog.operation_id.desc()).distinct()
        )
        operation_log_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db,
            query,
            query_object.page_num,
            query_object.page_size,
            is_page,
        )

        return operation_log_list

    @classmethod
    async def get_plugin_operation_log_export_list(
        cls,
        db: AsyncSession,
        query_object: PluginOperationLogExportQueryModel,
    ) -> list[dict[str, Any]]:
        """
        根据查询参数获取插件批量操作审计日志导出列表。

        :param db: orm对象
        :param query_object: 插件批量操作审计日志导出查询对象
        :return: 插件批量操作审计日志导出列表
        """
        query = (
            cls._build_operation_log_query(query_object)
            .order_by(SysPluginOperationLog.operation_id.desc())
            .limit(query_object.export_limit)
            .distinct()
        )
        export_list = await PageUtil.paginate(db, query, page_num=1, page_size=query_object.export_limit, is_page=False)

        return export_list

    @classmethod
    def _build_operation_log_query(
        cls,
        query_object: PluginOperationLogPageQueryModel | PluginOperationLogExportQueryModel,
    ) -> Any:
        """
        构建插件操作审计日志基础查询。

        :param query_object: 插件操作审计日志查询对象
        :return: SQLAlchemy 查询对象
        """
        return select(SysPluginOperationLog).where(
            SysPluginOperationLog.operation == query_object.operation if query_object.operation else True,
            SysPluginOperationLog.status == query_object.status if query_object.status else True,
            cls._build_plugin_ids_filter(query_object.plugin_id),
            cls._build_operation_log_time_filter(query_object),
        )

    @staticmethod
    def _build_plugin_ids_filter(plugin_id: str | None) -> Any:
        """
        构建插件 ID JSON 数组边界匹配条件。

        :param plugin_id: 插件ID
        :return: SQLAlchemy 过滤条件
        """
        if not plugin_id:
            return True

        escaped_plugin_id = escape_sql_like(plugin_id)
        return or_(
            SysPluginOperationLog.plugin_ids == f'["{plugin_id}"]',
            SysPluginOperationLog.plugin_ids.like(f'["{escaped_plugin_id}",%', escape='\\'),
            SysPluginOperationLog.plugin_ids.like(f'%, "{escaped_plugin_id}",%', escape='\\'),
            SysPluginOperationLog.plugin_ids.like(f'%, "{escaped_plugin_id}"]', escape='\\'),
            SysPluginOperationLog.plugin_ids.like(f'%,"{escaped_plugin_id}",%', escape='\\'),
            SysPluginOperationLog.plugin_ids.like(f'%,"{escaped_plugin_id}"]', escape='\\'),
        )

    @staticmethod
    def _build_operation_log_time_filter(
        query_object: PluginOperationLogPageQueryModel | PluginOperationLogExportQueryModel,
    ) -> Any:
        """
        构建插件操作审计日志时间范围条件。

        :param query_object: 插件操作审计日志查询对象
        :return: SQLAlchemy 时间范围条件或 True
        """
        if not query_object.begin_time or not query_object.end_time:
            return True

        return SysPluginOperationLog.create_time.between(
            datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
            datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
        )

    @classmethod
    async def get_plugin_operation_log_by_id(
        cls,
        db: AsyncSession,
        operation_id: int,
    ) -> SysPluginOperationLog | None:
        """
        根据操作日志 ID 查询插件批量操作审计日志。

        :param db: orm对象
        :param operation_id: 操作日志ID
        :return: 插件批量操作审计日志对象
        """
        operation_log = (
            (await db.execute(select(SysPluginOperationLog).where(SysPluginOperationLog.operation_id == operation_id)))
            .scalars()
            .first()
        )

        return operation_log

    @classmethod
    async def count_plugin_operation_logs_before(
        cls,
        db: AsyncSession,
        cutoff_time: datetime,
    ) -> int:
        """
        统计早于指定时间的插件批量操作审计日志数量。

        :param db: orm对象
        :param cutoff_time: 清理截止时间
        :return: 插件批量操作审计日志数量
        """
        matched_count = (
            await db.execute(
                select(func.count(SysPluginOperationLog.operation_id)).where(
                    SysPluginOperationLog.create_time < cutoff_time
                )
            )
        ).scalar_one()

        return int(matched_count)

    @classmethod
    async def delete_plugin_operation_logs_before(
        cls,
        db: AsyncSession,
        cutoff_time: datetime,
    ) -> int:
        """
        删除早于指定时间的插件批量操作审计日志。

        :param db: orm对象
        :param cutoff_time: 清理截止时间
        :return: 删除的插件批量操作审计日志数量
        """
        delete_result = await db.execute(
            delete(SysPluginOperationLog).where(SysPluginOperationLog.create_time < cutoff_time)
        )

        return int(delete_result.rowcount or 0)

    @classmethod
    async def get_sys_menu_by_id(cls, db: AsyncSession, menu_id: int) -> SysMenu | None:
        """
        根据菜单 ID 查询系统菜单。

        :param db: orm对象
        :param menu_id: 菜单ID
        :return: 系统菜单对象
        """
        menu = (await db.execute(select(SysMenu).where(SysMenu.menu_id == menu_id))).scalars().first()

        return menu

    @classmethod
    async def get_sys_menu_by_perms(cls, db: AsyncSession, perms: str) -> SysMenu | None:
        """
        根据权限标识查询系统菜单。

        :param db: orm对象
        :param perms: 权限标识
        :return: 系统菜单对象
        """
        menu = (await db.execute(select(SysMenu).where(SysMenu.perms == perms))).scalars().first()

        return menu

    @classmethod
    async def get_plugin_menu_by_menu_id(cls, db: AsyncSession, menu_id: int) -> SysPluginMenu | None:
        """
        根据菜单 ID 查询插件菜单关联。

        :param db: orm对象
        :param menu_id: 菜单ID
        :return: 插件菜单关联对象
        """
        plugin_menu = (
            (await db.execute(select(SysPluginMenu).where(SysPluginMenu.menu_id == menu_id))).scalars().first()
        )

        return plugin_menu

    @classmethod
    async def get_sys_menu_by_route(
        cls,
        db: AsyncSession,
        parent_id: int,
        path: str,
        component: str,
    ) -> SysMenu | None:
        """
        根据父级、路由路径和组件路径查询系统菜单。

        :param db: orm对象
        :param parent_id: 父菜单ID
        :param path: 路由路径
        :param component: 组件路径
        :return: 系统菜单对象
        """
        menu = (
            (
                await db.execute(
                    select(SysMenu).where(
                        SysMenu.parent_id == parent_id,
                        SysMenu.path == path,
                        SysMenu.component == component,
                    )
                )
            )
            .scalars()
            .first()
        )

        return menu

    @classmethod
    async def get_sys_menu_by_name_path(
        cls,
        db: AsyncSession,
        parent_id: int,
        menu_name: str,
        path: str,
    ) -> SysMenu | None:
        """
        根据父级、菜单名称和路由路径查询系统菜单。

        :param db: orm对象
        :param parent_id: 父菜单ID
        :param menu_name: 菜单名称
        :param path: 路由路径
        :return: 系统菜单对象
        """
        menu = (
            (
                await db.execute(
                    select(SysMenu).where(
                        SysMenu.parent_id == parent_id,
                        SysMenu.menu_name == menu_name,
                        SysMenu.path == path,
                    )
                )
            )
            .scalars()
            .first()
        )

        return menu

    @classmethod
    async def add_sys_menu(cls, db: AsyncSession, menu: MenuModel) -> SysMenu:
        """
        新增系统菜单。

        :param db: orm对象
        :param menu: 菜单对象
        :return: 新增后的系统菜单对象
        """
        db_menu = SysMenu(**menu.model_dump(exclude_unset=True))
        db.add(db_menu)
        await db.flush()

        return db_menu

    @classmethod
    async def update_sys_menu(cls, db: AsyncSession, menu: dict) -> None:
        """
        更新系统菜单。

        :param db: orm对象
        :param menu: 菜单更新字典
        :return: None
        """
        await db.execute(update(SysMenu), [menu])

    @classmethod
    async def update_sys_menu_status_by_ids(cls, db: AsyncSession, menu_ids: list[int], status: str) -> None:
        """
        批量更新系统菜单状态。

        :param db: orm对象
        :param menu_ids: 菜单ID列表
        :param status: 菜单状态
        :return: None
        """
        if menu_ids:
            await db.execute(update(SysMenu).where(SysMenu.menu_id.in_(menu_ids)).values(status=status))
