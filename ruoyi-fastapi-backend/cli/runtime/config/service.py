from typing import Any, Literal

from cli.exit_codes import ARGUMENT_ERROR, DATABASE_ERROR, REDIS_ERROR

from .gateway import ConfigInfrastructureGateway
from .support import ConfigDomainSupport


class ConfigRuntimeService:
    """
    参数配置运行时服务。

    该服务作为参数配置运行时 facade，对外统一暴露参数配置列表、详情、
    写入、缓存刷新与一致性诊断入口。

    :param infrastructure_gateway: 参数配置基础设施网关
    :param domain_support: 参数配置领域支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: ConfigInfrastructureGateway | None = None,
        domain_support: ConfigDomainSupport | None = None,
    ) -> None:
        """
        初始化参数配置运行时服务。

        :param infrastructure_gateway: 参数配置基础设施网关
        :param domain_support: 参数配置领域支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or ConfigInfrastructureGateway()
        self.domain_support = domain_support or ConfigDomainSupport(self.infrastructure_gateway)

    @staticmethod
    def build_cli_config_model(config_vo_module: Any, config_record: Any) -> Any | None:
        """
        将 ORM 配置记录显式转换为 CLI 可用的配置模型。

        `ConfigModel` 当前未统一开启 `populate_by_name`，因此 CLI 侧在处理
        ORM 蛇形字段对象时，需要主动映射为驼峰 alias 输入，避免详情查询结果
        被静默序列化为空。

        :param config_vo_module: 配置 VO 模块
        :param config_record: ORM 配置记录
        :return: CLI 可用配置模型
        """
        if config_record is None:
            return None
        return config_vo_module.ConfigModel(
            configId=getattr(config_record, 'config_id', None),
            configName=getattr(config_record, 'config_name', None),
            configKey=getattr(config_record, 'config_key', None),
            configValue=getattr(config_record, 'config_value', None),
            configType=getattr(config_record, 'config_type', None),
            createBy=getattr(config_record, 'create_by', None),
            createTime=getattr(config_record, 'create_time', None),
            updateBy=getattr(config_record, 'update_by', None),
            updateTime=getattr(config_record, 'update_time', None),
            remark=getattr(config_record, 'remark', None),
        )

    async def load_config_from_database(
        self,
        config_key: str,
    ) -> tuple[Any | None, dict[str, Any] | None] | dict[str, Any]:
        """
        从数据库加载参数配置。

        :param config_key: 参数键名
        :return: 成功时返回配置模型与序列化结果，失败时返回错误结果字典
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        config_dao = self.infrastructure_gateway.get_config_dao()
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        try:
            async with async_session_local() as session:
                config_record = await config_dao.get_config_detail_by_info(
                    session,
                    config_vo_module.ConfigModel(configKey=config_key),
                )
        except Exception as exc:
            return {'ok': False, 'message': '读取参数配置失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        database_model = self.build_cli_config_model(config_vo_module, config_record)
        return database_model, self.domain_support.serialize_config_model(database_model)

    async def load_config_from_cache(
        self,
        config_key: str,
    ) -> tuple[str | None, dict[str, Any] | None] | dict[str, Any]:
        """
        从缓存加载参数配置。

        :param config_key: 参数键名
        :return: 成功时返回原始缓存值与序列化结果，失败时返回错误结果字典
        """
        redis = None
        redis_util = self.infrastructure_gateway.get_redis_util()
        config_service = self.infrastructure_gateway.get_config_service()
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            redis = await redis_util.create_redis_pool(log_enabled=False)
            cache_value = await config_service.query_config_list_from_cache_services(redis, config_key)
            return cache_value, self.domain_support.serialize_cache_payload(config_key, cache_value)
        except redis_error as exc:
            return {'ok': False, 'message': '读取参数缓存失败', 'error': str(exc), 'exit_code': REDIS_ERROR}
        finally:
            if redis is not None:
                await redis.close()

    async def list_configs(
        self,
        config_name: str = '',
        config_key: str = '',
        config_type: Literal['Y', 'N'] | None = None,
        begin_date: str = '',
        end_date: str = '',
        *,
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询参数配置列表。

        :param config_name: 参数名称过滤条件
        :param config_key: 参数键名过滤条件
        :param config_type: 参数类型过滤条件
        :param begin_date: 开始日期
        :param end_date: 结束日期
        :param paged: 是否开启分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: CLI 标准结果字典
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        config_service = self.infrastructure_gateway.get_config_service()
        query_model = self.domain_support.build_config_query(
            config_name,
            config_key,
            config_type,
            begin_date,
            end_date,
            page_num,
            page_size,
        )
        try:
            async with async_session_local() as session:
                result = await config_service.get_config_list_services(session, query_model, is_page=paged)
        except Exception as exc:
            return {'ok': False, 'message': '读取参数配置列表失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        filters = self.domain_support.build_list_filters(
            config_name=config_name,
            config_key=config_key,
            config_type=config_type,
            begin_date=begin_date,
            end_date=end_date,
            paged=paged,
            page_num=page_num,
            page_size=page_size,
        )
        if paged and isinstance(result, self.infrastructure_gateway.get_page_model()):
            page_payload = result.model_dump(by_alias=True)
            page_payload['rows'] = [
                self.domain_support.sanitize_config_mapping(item) for item in page_payload.get('rows', [])
            ]
            return {'ok': True, 'filters': filters, 'page': page_payload}

        items = [self.domain_support.sanitize_config_mapping(item) for item in result]
        return {'ok': True, 'filters': filters, 'count': len(items), 'items': items}

    async def get_config(
        self,
        config_key: str,
        *,
        source: Literal['db', 'cache', 'both'] = 'both',
    ) -> dict[str, Any]:
        """
        按参数键读取配置详情。

        :param config_key: 参数键名
        :param source: 读取来源
        :return: CLI 标准结果字典
        """
        database_model: Any | None = None
        database_payload: dict[str, Any] | None = None
        cache_value: str | None = None
        cache_payload: dict[str, Any] | None = None

        if source in {'db', 'both'}:
            database_result = await self.load_config_from_database(config_key)
            if isinstance(database_result, dict):
                return database_result
            database_model, database_payload = database_result

        if source in {'cache', 'both'}:
            cache_result = await self.load_config_from_cache(config_key)
            if isinstance(cache_result, dict):
                error_payload = {**cache_result, 'source': source}
                if database_payload is not None:
                    error_payload['database'] = database_payload
                return error_payload
            cache_value, cache_payload = cache_result

        if source == 'db' and database_payload is None:
            return self.domain_support.build_missing_config_result(config_key, source)
        if source == 'cache' and cache_payload is None:
            return self.domain_support.build_missing_config_result(config_key, source)
        if source == 'both' and database_payload is None and cache_payload is None:
            return self.domain_support.build_missing_config_result(config_key, source)

        payload = {'ok': True, 'key': config_key, 'source': source}
        if source in {'db', 'both'}:
            payload['database'] = database_payload
        if source in {'cache', 'both'}:
            payload['cache'] = cache_payload
        if source == 'both':
            payload['inSync'] = (database_model.config_value if database_model else None) == cache_value
        return payload

    async def set_config(
        self,
        config_key: str,
        config_value: str,
        *,
        config_name: str | None = None,
        config_type: Literal['Y', 'N'] | None = None,
        remark: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        新增或更新参数配置，并同步缓存。

        :param config_key: 参数键名
        :param config_value: 参数键值
        :param config_name: 参数名称
        :param config_type: 参数类型
        :param remark: 备注
        :param dry_run: 是否仅执行演练
        :return: CLI 标准结果字典
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        config_dao = self.infrastructure_gateway.get_config_dao()
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        redis_util = self.infrastructure_gateway.get_redis_util()
        redis_init_key_config = self.infrastructure_gateway.get_redis_init_key_config()
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        existing_config = None
        target_config = None
        try:
            async with async_session_local() as session:
                config_record = await config_dao.get_config_detail_by_info(
                    session,
                    config_vo_module.ConfigModel(configKey=config_key),
                )
                existing_config = self.build_cli_config_model(config_vo_module, config_record)
                if existing_config is None and not config_name:
                    return {
                        'ok': False,
                        'message': '新增参数配置时必须传入 --name',
                        'exit_code': ARGUMENT_ERROR,
                    }

                target_config = self.domain_support.build_target_config_model(
                    config_key,
                    config_value,
                    config_name,
                    config_type,
                    remark,
                    existing_config,
                )
                if dry_run:
                    return {
                        'ok': True,
                        'message': '参数配置演练完成，未执行实际写入',
                        'dryRun': True,
                        'action': 'update' if existing_config else 'create',
                        'config': self.domain_support.serialize_config_model(target_config),
                    }

                if existing_config:
                    await config_dao.edit_config_dao(session, target_config.model_dump(exclude_none=True))
                else:
                    await config_dao.add_config_dao(session, target_config)
                await session.commit()
        except Exception as exc:
            return {'ok': False, 'message': '写入参数配置失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        redis = None
        try:
            redis = await redis_util.create_redis_pool(log_enabled=False)
            await redis.set(f'{redis_init_key_config.SYS_CONFIG.key}:{config_key}', config_value)
        except redis_error as exc:
            return {
                'ok': False,
                'message': '参数配置已写入数据库，但同步缓存失败',
                'error': str(exc),
                'config': self.domain_support.serialize_config_model(target_config),
                'databaseCommitted': True,
                'exit_code': REDIS_ERROR,
            }
        finally:
            if redis is not None:
                await redis.close()

        return {
            'ok': True,
            'message': '参数配置已同步到数据库和缓存',
            'action': 'update' if existing_config else 'create',
            'config': self.domain_support.serialize_config_model(target_config),
        }

    async def sync_config_cache(self) -> dict[str, Any]:
        """
        刷新参数配置缓存。

        :return: CLI 标准结果字典
        """
        redis = None
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        config_service = self.infrastructure_gateway.get_config_service()
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        redis_util = self.infrastructure_gateway.get_redis_util()
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with async_session_local() as session:
                config_list = await config_service.get_config_list_services(
                    session,
                    config_vo_module.ConfigPageQueryModel(),
                    is_page=False,
                )
                redis = await redis_util.create_redis_pool(log_enabled=False)
                await config_service.init_cache_sys_config_services(session, redis)
        except redis_error as exc:
            return {'ok': False, 'message': '刷新参数缓存失败', 'error': str(exc), 'exit_code': REDIS_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '刷新参数缓存失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        finally:
            if redis is not None:
                await redis.close()

        return {'ok': True, 'message': '参数缓存刷新成功', 'count': len(config_list)}

    async def diagnose_config(self, *, sample_limit: int = 10) -> dict[str, Any]:
        """
        诊断数据库参数配置与 Redis 缓存的一致性状态。

        :param sample_limit: 示例键名输出上限
        :return: CLI 标准结果字典
        """
        redis = None
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        config_service = self.infrastructure_gateway.get_config_service()
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        redis_util = self.infrastructure_gateway.get_redis_util()
        redis_init_key_config = self.infrastructure_gateway.get_redis_init_key_config()
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with async_session_local() as session:
                config_list = await config_service.get_config_list_services(
                    session,
                    config_vo_module.ConfigPageQueryModel(),
                    is_page=False,
                )
            redis = await redis_util.create_redis_pool(log_enabled=False)
            cache_prefix = f'{redis_init_key_config.SYS_CONFIG.key}:'
            cache_keys = sorted(await redis.keys(f'{cache_prefix}*'))
            cache_values = await redis.mget(*cache_keys) if cache_keys else []
        except redis_error as exc:
            return {'ok': False, 'message': '读取参数缓存诊断信息失败', 'error': str(exc), 'exit_code': REDIS_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '读取参数配置诊断信息失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        finally:
            if redis is not None:
                await redis.close()

        database_map = {str(item.get('configKey')): str(item.get('configValue', '')) for item in config_list}
        cache_map = {
            cache_key.replace(cache_prefix, '', 1): '' if cache_value is None else str(cache_value)
            for cache_key, cache_value in zip(cache_keys, cache_values, strict=False)
        }
        missing_in_cache = sorted(key for key in database_map if key not in cache_map)
        orphan_in_cache = sorted(key for key in cache_map if key not in database_map)
        mismatch_keys = sorted(
            key for key, database_value in database_map.items() if key in cache_map and database_value != cache_map[key]
        )
        in_sync = not missing_in_cache and not orphan_in_cache and not mismatch_keys
        return {
            'ok': in_sync,
            'message': '参数配置数据库与缓存一致' if in_sync else '参数配置存在数据库与缓存不一致项',
            'databaseCount': len(database_map),
            'cacheCount': len(cache_map),
            'missingInCacheCount': len(missing_in_cache),
            'orphanInCacheCount': len(orphan_in_cache),
            'mismatchCount': len(mismatch_keys),
            'sampleLimit': sample_limit,
            'missingInCache': missing_in_cache[:sample_limit],
            'orphanInCache': orphan_in_cache[:sample_limit],
            'mismatchKeys': mismatch_keys[:sample_limit],
        }


CONFIG_RUNTIME = ConfigRuntimeService()
