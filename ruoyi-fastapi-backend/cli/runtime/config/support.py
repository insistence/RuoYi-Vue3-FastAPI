from datetime import datetime
from typing import Any, Literal

from cli.exit_codes import RUNTIME_ERROR
from cli.runtime.base import RUNTIME_OPERATOR, RuntimeOperatorService

from .gateway import ConfigInfrastructureGateway


class ConfigDomainSupport:
    """
    参数配置领域支持对象。

    该对象负责操作者解析、配置脱敏、序列化、查询模型构建与缺失结果构建，
    避免主运行时服务继续承载大量领域规则。

    :param infrastructure_gateway: 参数配置基础设施网关
    """

    def __init__(
        self,
        infrastructure_gateway: ConfigInfrastructureGateway,
        operator_service: RuntimeOperatorService = RUNTIME_OPERATOR,
    ) -> None:
        """
        初始化参数配置领域支持对象。

        :param infrastructure_gateway: 参数配置基础设施网关
        :param operator_service: 运行时操作者解析服务
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway
        self.operator_service = operator_service

    def sanitize_config_mapping(self, config_mapping: dict[str, Any]) -> dict[str, Any]:
        """
        对配置字典进行脱敏处理。

        :param config_mapping: 原始配置字典
        :return: 脱敏后的配置字典
        """
        return self.infrastructure_gateway.get_log_sanitizer().sanitize_data(config_mapping)

    def serialize_config_model(self, config_model: Any | None) -> dict[str, Any] | None:
        """
        将配置模型序列化为 CLI 输出字典。

        :param config_model: 配置模型对象
        :return: 序列化后的配置字典
        """
        if config_model is None or config_model.config_id is None:
            return None
        return self.sanitize_config_mapping(config_model.model_dump(by_alias=True, exclude_none=True))

    def serialize_cache_payload(self, config_key: str, config_value: str | None) -> dict[str, Any] | None:
        """
        将缓存中的配置值序列化为 CLI 输出字典。

        :param config_key: 参数键名
        :param config_value: 参数键值
        :return: 序列化后的缓存配置字典
        """
        if config_value is None:
            return None
        return self.sanitize_config_mapping({'configKey': config_key, 'configValue': config_value})

    @staticmethod
    def build_missing_config_result(
        config_key: str,
        source: Literal['db', 'cache', 'both'],
    ) -> dict[str, Any]:
        """
        构建配置不存在的统一结果。

        :param config_key: 参数键名
        :param source: 读取来源
        :return: 配置不存在的结果字典
        """
        message = f'参数缓存不存在：{config_key}' if source == 'cache' else f'参数配置不存在：{config_key}'
        return {'ok': False, 'message': message, 'source': source, 'exit_code': RUNTIME_ERROR}

    def build_config_query(
        self,
        config_name: str,
        config_key: str,
        config_type: Literal['Y', 'N'] | None,
        begin_date: str,
        end_date: str,
        page_num: int,
        page_size: int,
    ) -> Any:
        """
        构建配置列表查询对象。

        :param config_name: 参数名称过滤条件
        :param config_key: 参数键名过滤条件
        :param config_type: 参数类型过滤条件
        :param begin_date: 开始日期
        :param end_date: 结束日期
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 配置分页查询模型
        """
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        return config_vo_module.ConfigPageQueryModel(
            configName=config_name or None,
            configKey=config_key or None,
            configType=config_type,
            beginTime=begin_date or None,
            endTime=end_date or None,
            pageNum=page_num,
            pageSize=page_size,
        )

    def build_target_config_model(
        self,
        config_key: str,
        config_value: str,
        config_name: str | None,
        config_type: Literal['Y', 'N'] | None,
        remark: str | None,
        existing_config: Any | None,
    ) -> Any:
        """
        基于当前状态构建目标配置模型。

        :param config_key: 参数键名
        :param config_value: 参数键值
        :param config_name: 参数名称
        :param config_type: 参数类型
        :param remark: 参数备注
        :param existing_config: 已存在的配置模型
        :return: 目标配置模型
        """
        operator = self.operator_service.resolve_operator()
        current_time = datetime.now()
        common_constant = self.infrastructure_gateway.get_common_constant()
        config_vo_module = self.infrastructure_gateway.get_config_vo_module()
        default_config_type = existing_config.config_type if existing_config else common_constant.NO
        target_config = config_vo_module.ConfigModel(
            configId=existing_config.config_id if existing_config else None,
            configName=config_name
            if config_name is not None
            else (existing_config.config_name if existing_config else None),
            configKey=config_key,
            configValue=config_value,
            configType=config_type if config_type is not None else default_config_type,
            createBy=existing_config.create_by if existing_config else operator,
            createTime=existing_config.create_time if existing_config else current_time,
            updateBy=operator,
            updateTime=current_time,
            remark=remark if remark is not None else (existing_config.remark if existing_config else None),
        )
        target_config.validate_fields()
        return target_config

    def build_list_filters(
        self,
        *,
        config_name: str,
        config_key: str,
        config_type: Literal['Y', 'N'] | None,
        begin_date: str,
        end_date: str,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> dict[str, Any]:
        """
        构建配置列表过滤条件。

        :param config_name: 参数名称
        :param config_key: 参数键名
        :param config_type: 参数类型
        :param begin_date: 开始日期
        :param end_date: 结束日期
        :param paged: 是否分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 过滤条件字典
        """
        return {
            'configName': config_name,
            'configKey': config_key,
            'configType': config_type,
            'beginDate': begin_date,
            'endDate': end_date,
            'paged': paged,
            'pageNum': page_num,
            'pageSize': page_size,
        }
