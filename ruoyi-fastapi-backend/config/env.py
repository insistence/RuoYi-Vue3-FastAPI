import argparse
import configparser
import json
import os
import re
import secrets
import sys
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from exceptions.exception import DataSourceNotFoundException


class AppSettings(BaseSettings):
    """
    应用配置
    """

    app_env: str = 'dev'
    app_name: str = 'RuoYi-FasAPI'
    app_root_path: str = '/dev-api'
    app_host: str = '0.0.0.0'
    app_port: int = 9099
    app_version: str = '1.0.0'
    app_release_id: str = ''
    app_reload: bool = True
    app_workers: int = 1
    app_ip_location_query: bool = True
    app_same_time_login: bool = True
    app_demo_mode: bool = False
    app_disable_swagger: bool = False
    app_disable_redoc: bool = False
    app_trusted_proxy_ips: str = '127.0.0.1,::1'
    app_trusted_proxy_hops: int = 1
    app_default_enabled_plugins: str = 'ai'


class JwtSettings(BaseSettings):
    """
    Jwt配置
    """

    jwt_secret_key: str = Field(default_factory=lambda: secrets.token_hex(32))
    jwt_algorithm: str = 'HS256'
    jwt_expire_minutes: int = 1440
    jwt_redis_expire_minutes: int = 30

    @field_validator('jwt_secret_key', mode='before')
    @classmethod
    def generate_empty_secret_key(cls, value: object) -> object:
        """
        Jwt密钥未配置时生成随机值。

        :param value: 环境变量中的Jwt密钥
        :return: 已配置的Jwt密钥或随机生成的密钥
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return secrets.token_hex(32)
        return value


class DataSourceSettings(BaseModel):
    """
    单个数据源配置
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    db_type: Literal['mysql', 'postgresql']
    db_host: str = Field(min_length=1)
    db_port: int = Field(ge=1, le=65535)
    db_username: str = Field(min_length=1)
    db_password: SecretStr
    db_database: str = Field(min_length=1)

    db_echo: bool = True
    db_connect_timeout: int = Field(default=10, gt=0)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_size: int = Field(default=20, ge=1)
    db_pool_recycle: int = Field(default=3600, ge=-1)
    db_pool_timeout: int = Field(default=30, gt=0)
    db_required: bool = True

    @computed_field
    @property
    def sqlglot_parse_dialect(self) -> str:
        """
        获取SQLGlot解析方言

        :return: SQLGlot解析方言
        """
        if self.db_type == 'postgresql':
            return 'postgres'
        return self.db_type


DATA_SOURCE_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


class DataBaseSettings(BaseSettings):
    """
    数据库集合配置
    """

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    db_default_source: str = 'primary'
    db_sources: Annotated[dict[str, DataSourceSettings], NoDecode] = Field(default_factory=dict)

    @field_validator('db_sources', mode='before')
    @classmethod
    def parse_sources_json(cls, value: object) -> object:
        """
        解析显式传入的数据源JSON字符串

        :param value: 数据源配置原始值
        :return: 解析后的数据源配置
        """
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise ValueError('DB_SOURCES JSON 格式错误') from None

    @model_validator(mode='after')
    def validate_sources(self) -> 'DataBaseSettings':
        """
        校验数据源集合和默认数据源配置

        :return: 数据库集合配置
        """
        if not self.db_sources:
            raise ValueError('DB_SOURCES 不能为空')
        if self.db_default_source not in self.db_sources:
            raise ValueError(f'默认数据源不存在：{self.db_default_source}')
        for name in self.db_sources:
            if not DATA_SOURCE_NAME_PATTERN.fullmatch(name):
                raise ValueError(f'数据源名称不合法：{name}')
        return self

    def get_source(self, name: str | None = None) -> DataSourceSettings:
        """
        获取指定数据源配置

        :param name: 数据源名称
        :return: 数据源配置
        """
        source_name = name or self.db_default_source
        try:
            return self.db_sources[source_name]
        except KeyError as exc:
            raise DataSourceNotFoundException(source_name) from exc

    @property
    def default_source(self) -> DataSourceSettings:
        """
        获取默认数据源配置

        :return: 默认数据源配置
        """
        return self.get_source()


class RedisSettings(BaseSettings):
    """
    Redis配置
    """

    redis_host: str = '127.0.0.1'
    redis_port: int = 6379
    redis_username: str = ''
    redis_password: str = ''
    redis_database: int = 2


class LogSettings(BaseSettings):
    """
    日志与队列配置
    """

    log_mask_enabled: bool = True
    log_mask_placeholder: str = '******'
    log_mask_fields: str = (
        'password,old_password,new_password,confirm_password,api_key,token,access_token,refresh_token,'
        'authorization,client_secret,secret,secret_key,private_key,private_key_pem,credential,credentials,'
        'sms_code,captcha_code,system_prompt'
    )
    log_partial_mask_fields: str = 'phonenumber,phone,mobile,email'
    log_config_secret_patterns: str = 'password,token,secret,key,private,credential,access,jwt,captcha,sms'
    log_stream_key: str = 'log:stream'
    log_stream_group: str = 'log_aggregator'
    log_stream_consumer_prefix: str = 'worker'
    log_stream_batch_size: int = 100
    log_stream_block_ms: int = 2000
    log_stream_maxlen: int = 100000
    log_stream_claim_idle_ms: int = 60000
    log_stream_claim_interval_ms: int = 5000
    log_stream_claim_batch_size: int = 100
    log_stream_dedup_ttl: int = 3600
    log_stream_dedup_prefix: str = 'log:dedup'

    loguru_json: bool = False
    loguru_level: str = 'INFO'
    loguru_stdout: bool = True
    log_file_enabled: bool = True
    log_file_base_dir: str = 'logs'
    loguru_rotation: str = '50MB'
    loguru_retention: str = '30 days'
    loguru_compression: str = 'zip'
    log_instance_id: str = 'prod'
    log_service_name: str = 'ruoyi-fastapi-backend'
    log_worker_id: str = 'auto'


class TransportCryptoSettings(BaseSettings):
    """
    传输层加解密配置
    """

    transport_crypto_enabled: bool = True
    transport_crypto_mode: Literal['off', 'optional', 'required'] = 'optional'
    transport_crypto_algorithm: str = 'RSA_OAEP_AES_256_GCM'
    transport_crypto_kid: str = 'default'
    transport_crypto_public_key: str = ''
    transport_crypto_private_key: str = ''
    transport_crypto_legacy_key_pairs: str = '[]'
    transport_crypto_rsa_key_size: int = 2048
    transport_crypto_public_key_ttl_seconds: int = 3600
    transport_crypto_frontend_config_ttl_seconds: int = 300
    transport_crypto_max_get_url_length: int = 4096
    transport_crypto_clock_skew_seconds: int = 120
    transport_crypto_replay_ttl_seconds: int = 300
    transport_crypto_enabled_paths: str = ''
    transport_crypto_required_paths: str = ''
    transport_crypto_exclude_paths: str = (
        '/openapi.json,/docs,/docs/oauth2-redirect,/redoc,'
        '/transport/crypto/frontend-config,/transport/crypto/public-key,/common/download,/common/download/resource,'
        '/common/files,/system/file/download'
    )


class PluginDependencyPolicySettings(BaseSettings):
    """
    插件依赖安装策略配置
    """

    plugin_dependency_policy_mode: str = 'dev=explicit,test=plan_only,stage=locked,prod=plan_only'
    plugin_dependency_allow_prod_install: bool = False
    plugin_dependency_require_yes: bool = True
    plugin_dependency_require_allowlist: bool | None = None
    plugin_dependency_require_lockfile: bool | None = None
    plugin_dependency_lockfile: str = ''
    plugin_dependency_allowlist: str = ''
    plugin_dependency_offline_dir: str = ''
    plugin_dependency_pip_index_url: str = ''
    plugin_dependency_npm_registry: str = ''
    plugin_dependency_install_timeout: int = 600


class GenSettings:
    """
    代码生成配置
    """

    author = 'insistence'
    package_name = 'module_admin.system'
    auto_remove_pre = False
    table_prefix = 'sys_'
    allow_overwrite = False

    GEN_PATH = 'vf_admin/gen_path'

    def __init__(self) -> None:
        if not os.path.exists(self.GEN_PATH):
            os.makedirs(self.GEN_PATH)


class UploadSettings:
    """
    上传配置
    """

    UPLOAD_PREFIX = '/profile'
    UPLOAD_PATH = 'vf_admin/upload_path'
    PRIVATE_UPLOAD_PATH = 'vf_admin/private_upload_path'
    FILE_TRASH_PATH = 'vf_admin/file_trash_path'
    FILE_RECONCILE_QUARANTINE_PATH = 'vf_admin/file_reconcile_quarantine_path'
    UPLOAD_MACHINE = 'A'
    DEFAULT_ALLOWED_EXTENSION = [
        # 图片
        'bmp',
        'gif',
        'jpg',
        'jpeg',
        'png',
        # word excel powerpoint
        'doc',
        'docx',
        'xls',
        'xlsx',
        'ppt',
        'pptx',
        'html',
        'htm',
        'txt',
        # 压缩文件
        'rar',
        'zip',
        'gz',
        'bz2',
        # 视频格式
        'mp4',
        'avi',
        'rmvb',
        # pdf
        'pdf',
    ]
    DOWNLOAD_PATH = 'vf_admin/download_path'
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self) -> None:
        if not os.path.exists(self.UPLOAD_PATH):
            os.makedirs(self.UPLOAD_PATH)
        if not os.path.exists(self.PRIVATE_UPLOAD_PATH):
            os.makedirs(self.PRIVATE_UPLOAD_PATH)
        if not os.path.exists(self.FILE_TRASH_PATH):
            os.makedirs(self.FILE_TRASH_PATH)
        if not os.path.exists(self.FILE_RECONCILE_QUARANTINE_PATH):
            os.makedirs(self.FILE_RECONCILE_QUARANTINE_PATH)
        if not os.path.exists(self.DOWNLOAD_PATH):
            os.makedirs(self.DOWNLOAD_PATH)


class CachePathConfig:
    """
    缓存目录配置
    """

    PATH = os.path.join(os.path.abspath(os.getcwd()), 'caches')
    PATHSTR = 'caches'


class GetConfig:
    """
    获取配置
    """

    def __init__(self) -> None:
        self.run_env = self.parse_cli_args()

    def get_app_config(self) -> AppSettings:
        """
        获取应用配置
        """
        # 实例化应用配置模型
        return AppSettings()

    def get_jwt_config(self) -> JwtSettings:
        """
        获取Jwt配置
        """
        # 实例化Jwt配置模型
        return JwtSettings()

    def get_database_config(self) -> DataBaseSettings:
        """
        获取数据库配置
        """
        # 实例化数据库配置模型
        return DataBaseSettings()

    def get_redis_config(self) -> RedisSettings:
        """
        获取Redis配置
        """
        # 实例化Redis配置模型
        return RedisSettings()

    def get_log_config(self) -> LogSettings:
        """
        获取日志配置
        """
        return LogSettings()

    def get_transport_crypto_config(self) -> TransportCryptoSettings:
        """
        获取传输层加解密配置
        """
        return TransportCryptoSettings()

    def get_plugin_dependency_policy_config(self) -> PluginDependencyPolicySettings:
        """
        获取插件依赖安装策略配置
        """
        return PluginDependencyPolicySettings()

    def get_gen_config(self) -> GenSettings:
        """
        获取代码生成配置
        """
        # 实例化代码生成配置
        return GenSettings()

    def get_upload_config(self) -> UploadSettings:
        """
        获取上传配置
        """
        # 实例上传配置
        return UploadSettings()

    @staticmethod
    def parse_cli_args() -> str:
        """
        解析命令行参数并加载对应环境配置。

        ``run_env`` 用于选择 ``.env.*`` 配置文件，实际应用环境以配置
        文件中的 ``APP_ENV`` 为准。

        :return: 当前加载的运行环境配置名称
        """
        run_env = os.environ.get('APP_ENV', '')
        # 检查是否在alembic环境中运行，如果是则跳过参数解析
        if 'alembic' in sys.argv[0] or any('alembic' in arg for arg in sys.argv):
            ini_config = configparser.ConfigParser()
            ini_config.read('alembic.ini', encoding='utf-8')
            if 'settings' in ini_config:
                # 获取env选项
                run_env = ini_config['settings'].get('env') or run_env
        elif 'uvicorn' in sys.argv[0]:
            # 使用uvicorn启动时，命令行参数需要按照uvicorn的文档进行配置，无法自定义参数
            pass
        else:
            # 使用argparse定义命令行参数
            parser = argparse.ArgumentParser(description='命令行参数')
            parser.add_argument('--env', type=str, default='', help='运行环境')
            # 解析命令行参数
            args, _ = parser.parse_known_args()
            run_env = args.env or run_env
        # 运行环境未指定时默认加载.env.dev
        run_env = run_env.strip() or 'dev'
        env_file = f'.env.{run_env}'
        # 加载配置，已通过外部命令设置的环境变量保持优先
        load_dotenv(env_file)
        return run_env


# 实例化获取配置类
get_config = GetConfig()
# 应用配置
AppConfig = get_config.get_app_config()
# Jwt配置
JwtConfig = get_config.get_jwt_config()
# 数据库配置
DataBaseConfig = get_config.get_database_config()
# Redis配置
RedisConfig = get_config.get_redis_config()
# 日志配置
LogConfig = get_config.get_log_config()
# 传输层加解密配置
TransportCryptoConfig = get_config.get_transport_crypto_config()
# 插件依赖安装策略配置
PluginDependencyPolicyConfig = get_config.get_plugin_dependency_policy_config()
# 代码生成配置
GenConfig = get_config.get_gen_config()
# 上传配置
UploadConfig = get_config.get_upload_config()
