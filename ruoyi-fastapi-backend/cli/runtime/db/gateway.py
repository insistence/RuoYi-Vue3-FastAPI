from importlib import import_module
from typing import Any


class DatabaseInfrastructureGateway:
    """
    数据库基础设施网关。

    该对象负责延迟加载数据库引擎、SQLAlchemy 和 Alembic 相关依赖，
    供数据库运行时 facade 与其协作对象统一复用。
    """

    @staticmethod
    def get_async_db_engine_factory() -> Any:
        """
        获取异步数据库引擎工厂函数。

        :return: 异步数据库引擎工厂函数
        """
        return import_module('config.database').create_async_db_engine

    @staticmethod
    def get_sync_db_engine_factory() -> Any:
        """
        获取同步数据库引擎工厂函数。

        :return: 同步数据库引擎工厂函数
        """
        return import_module('config.database').create_sync_db_engine

    @staticmethod
    def get_sqlalchemy_text() -> Any:
        """
        获取 SQLAlchemy `text` 构造函数。

        :return: SQLAlchemy `text` 函数
        """
        return import_module('sqlalchemy').text

    @staticmethod
    def get_alembic_config_class() -> Any:
        """
        获取 Alembic 配置类。

        :return: Alembic 配置类
        """
        return import_module('alembic.config').Config

    @staticmethod
    def get_alembic_script_directory_class() -> Any:
        """
        获取 Alembic 脚本目录类。

        :return: Alembic 脚本目录类
        """
        return import_module('alembic.script').ScriptDirectory
