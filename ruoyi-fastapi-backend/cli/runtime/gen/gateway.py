from importlib import import_module
from typing import Any


class GenInfrastructureGateway:
    """
    代码生成基础设施网关。

    该对象负责延迟加载 sqlglot、数据库会话、分页模型、配置对象、
    业务异常和代码生成服务依赖，供代码生成运行时 facade 与其协作对象统一复用。
    """

    @staticmethod
    def get_sqlglot_module() -> Any:
        """
        获取 `sqlglot` 模块。

        :return: `sqlglot` 模块
        """
        return import_module('sqlglot')

    @staticmethod
    def get_sqlglot_expressions_module() -> Any:
        """
        获取 `sqlglot.expressions` 模块。

        :return: `sqlglot.expressions` 模块
        """
        return import_module('sqlglot.expressions')

    @staticmethod
    def get_async_session_local() -> Any:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """
        return import_module('config.database').AsyncSessionLocal

    @staticmethod
    def get_page_model() -> Any:
        """
        获取分页模型类型。

        :return: 分页模型类型
        """
        return import_module('common.vo').PageModel

    @staticmethod
    def get_database_config() -> Any:
        """
        获取数据库配置对象。

        :return: 数据库配置对象
        """
        return import_module('config.env').DataBaseConfig

    @staticmethod
    def get_gen_config() -> Any:
        """
        获取代码生成配置对象。

        :return: 代码生成配置对象
        """
        return import_module('config.env').GenConfig

    @staticmethod
    def get_service_exception_class() -> type[Exception]:
        """
        获取业务异常类型。

        :return: 业务异常类型
        """
        return import_module('exceptions.exception').ServiceException

    @staticmethod
    def get_user_vo_module() -> Any:
        """
        获取用户 VO 模块。

        :return: 用户 VO 模块
        """
        return import_module('module_admin.entity.vo.user_vo')

    @staticmethod
    def get_gen_vo_module() -> Any:
        """
        获取代码生成 VO 模块。

        :return: 代码生成 VO 模块
        """
        return import_module('module_generator.entity.vo.gen_vo')

    @staticmethod
    def get_gen_table_service() -> Any:
        """
        获取代码生成服务类。

        :return: 代码生成服务类
        """
        return import_module('module_generator.service.gen_service').GenTableService

    @staticmethod
    def get_gen_table_column_service() -> Any:
        """
        获取代码生成字段服务类。

        :return: 代码生成字段服务类
        """
        return import_module('module_generator.service.gen_service').GenTableColumnService
