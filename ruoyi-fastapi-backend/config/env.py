import argparse
import configparser
import json
import os
import re
import secrets
import sys
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from exceptions.exception import DataSourceNotFoundException
from utils.time_util import TimezoneUtil


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
    app_timezone: str = 'Asia/Shanghai'

    @field_validator('app_timezone')
    @classmethod
    def validate_app_timezone(cls, value: str) -> str:
        """
        校验应用业务时区是否为有效的IANA时区名称。

        :param value: IANA时区名称
        :return: 去除首尾空格后的IANA时区名称
        """
        try:
            return TimezoneUtil.validate_timezone_name(value)
        except ValueError as exc:
            raise ValueError(f'APP_TIMEZONE: {exc}') from None


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
        '/common/files,/system/file/download,'
        '/.well-known/openid-configuration,/.well-known/oauth-authorization-server,'
        '/oauth2/authorize,/oauth2/token,/oauth2/userinfo,/oauth2/jwks,'
        '/oauth2/revoke,/oauth2/introspect,/oauth2/logout'
    )


class OidcSettings(BaseSettings):
    """
    OIDC/OAuth2 认证中心配置

    OIDC 默认关闭，关闭时只保留可安全解析的默认值，不要求发行者、签名密钥
    或不透明令牌 Pepper，从而保证现有 Legacy JWT 启动路径完全不变。
    """

    oidc_enabled: bool = False
    oidc_issuer: str = 'https://auth.example.com'
    oidc_public_base_url: str = 'https://auth.example.com'

    oidc_require_pkce: bool = True
    oidc_pkce_methods: str = 'S256'
    oidc_allowed_clock_skew_seconds: int = Field(default=60, ge=0)
    oidc_authorization_code_ttl_seconds: int = Field(default=90, gt=0)
    oidc_interaction_ttl_seconds: int = Field(default=300, gt=0)
    oidc_id_token_ttl_seconds: int = Field(default=300, gt=0)
    oidc_access_token_ttl_seconds: int = Field(default=600, gt=0)
    oidc_max_access_token_ttl_seconds: int = Field(default=1800, gt=0)
    oidc_refresh_token_idle_seconds: int = Field(default=604800, gt=0)
    oidc_refresh_token_absolute_seconds: int = Field(default=2592000, gt=0)

    oidc_sso_idle_seconds: int = Field(default=1800, gt=0)
    oidc_sso_absolute_seconds: int = Field(default=28800, gt=0)
    oidc_sso_remember_absolute_seconds: int = Field(default=604800, gt=0)
    oidc_sso_cookie_name: str = '__Host-ruoyi-sso'
    oidc_sso_cookie_secure: bool = True
    oidc_sso_cookie_samesite: Literal['lax', 'strict', 'none'] = 'lax'
    oidc_sso_cookie_domain: str | None = None

    oidc_signing_algorithm: Literal['RS256'] = 'RS256'
    oidc_signing_key_source: Literal['file', 'kms', 'hsm'] = 'file'
    oidc_signing_private_key_path: str = ''
    oidc_signing_key_encryption_key: str = ''
    oidc_active_kid: str = ''
    oidc_key_rotation_overlap_seconds: int = Field(default=86400, gt=0)

    oidc_token_hash_pepper: str = ''

    oidc_cors_allowed_origins: str = ''
    oidc_interaction_login_url: str = 'https://auth.example.com/auth-center/login'
    oidc_interaction_consent_url: str = 'https://auth.example.com/auth-center/consent'
    oidc_interaction_error_url: str = 'https://auth.example.com/auth-center/error'

    oidc_audit_retention_days: int = Field(default=180, gt=0)
    oidc_backchannel_logout_timeout_seconds: int = Field(default=5, gt=0)
    oidc_legacy_auth_isolation_enabled: bool = True
    OIDC_PEPPER_MIN_BYTES: ClassVar[int] = 32

    @staticmethod
    def _normalise_url(value: str, field_name: str, *, allow_empty: bool = False) -> str:
        """
        规范化并校验认证中心地址。

        :param value: 待校验的 URL 文本
        :param field_name: 配置字段名称
        :param allow_empty: 是否允许空值
        :return: 去除尾部斜杠且不含 query/fragment 的 URL
        :raises ValueError: URL 不是绝对 HTTP(S) 地址或含有不安全部分
        """
        value = value.strip().strip('\'"')
        if not value:
            if allow_empty:
                return ''
            raise ValueError(f'{field_name} 不能为空')
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError(f'{field_name} 必须是绝对 HTTP(S) URL')
        if parsed.username or parsed.password:
            raise ValueError(f'{field_name} 不得包含用户信息')
        if parsed.query or parsed.fragment:
            raise ValueError(f'{field_name} 不得包含 query 或 fragment')
        path = parsed.path.rstrip('/')
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, '', ''))

    @staticmethod
    def _is_local_http(url: str) -> bool:
        """
        判断 URL 是否属于仅开发环境允许的本机 HTTP 地址。

        :param url: 已解析的 URL
        :return: 是否为 localhost、127.0.0.1 或 ::1 的 HTTP 地址
        """
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        return parsed.scheme == 'http' and host in {'localhost', '127.0.0.1', '::1'}

    @property
    def pkce_method_list(self) -> tuple[str, ...]:
        """
        返回规范化后的 PKCE 方法集合。

        :return: 以逗号分隔配置解析出的 PKCE 方法
        """
        return tuple(item.strip() for item in self.oidc_pkce_methods.split(',') if item.strip())

    @property
    def cors_origin_list(self) -> tuple[str, ...]:
        """
        返回规范化后的、用于精确匹配的注册 Origin。

        :return: 去除空项和尾部斜杠后的 Origin 集合
        """
        return tuple(item.strip().rstrip('/') for item in self.oidc_cors_allowed_origins.split(',') if item.strip())

    def _validate_issuer_urls(self, app_env: str) -> None:
        """
        校验 issuer、公开基址及环境协议要求。

        :param app_env: 当前应用环境
        :raises ValueError: issuer 不安全、含路径前缀或公开地址不一致
        """
        if self.oidc_issuer != self.oidc_public_base_url:
            raise ValueError('OIDC_PUBLIC_BASE_URL 必须与 OIDC_ISSUER 一致')
        parsed = urlsplit(self.oidc_issuer)
        if parsed.path.rstrip('/'):
            raise ValueError('OIDC_ISSUER 不得包含路径前缀')
        if parsed.scheme != 'https' and not (
            app_env in {'dev', 'test', 'local'} and self._is_local_http(self.oidc_issuer)
        ):
            raise ValueError('OIDC_ISSUER 生产环境必须使用 HTTPS')
        if urlsplit(self.oidc_public_base_url).scheme != parsed.scheme:
            raise ValueError('OIDC_PUBLIC_BASE_URL 必须与 issuer 使用相同 scheme')

    def _validate_protocol_options(self) -> None:
        """
        校验 PKCE 和各类协议 TTL。

        :raises ValueError: 协议选项不符合统一认证安全边界
        """
        if not self.oidc_require_pkce:
            raise ValueError('OIDC_REQUIRE_PKCE 启用认证中心时必须为 true')
        if self.pkce_method_list != ('S256',):
            raise ValueError('OIDC_PKCE_METHODS 目前只能配置为 S256')
        if self.oidc_access_token_ttl_seconds > self.oidc_max_access_token_ttl_seconds:
            raise ValueError('OIDC_MAX_ACCESS_TOKEN_TTL_SECONDS 不能小于默认 Access Token TTL')
        if self.oidc_refresh_token_idle_seconds > self.oidc_refresh_token_absolute_seconds:
            raise ValueError('Refresh Token 闲置 TTL 不能大于绝对 TTL')
        if self.oidc_sso_absolute_seconds > self.oidc_sso_remember_absolute_seconds:
            raise ValueError('SSO remember-me TTL 不能小于普通 SSO 绝对 TTL')

    def _validate_secret_material(self) -> None:
        """
        校验 OIDC Pepper、签名密钥定位信息和 Legacy 隔离开关。

        :raises ValueError: Pepper、密钥或隔离策略不符合要求
        """
        if not self.oidc_legacy_auth_isolation_enabled:
            raise ValueError('OIDC_LEGACY_AUTH_ISOLATION_ENABLED 启用认证中心时必须为 true')
        pepper = self.oidc_token_hash_pepper.strip()
        if len(pepper.encode('utf-8')) < self.OIDC_PEPPER_MIN_BYTES:
            raise ValueError('OIDC_TOKEN_HASH_PEPPER 至少需要 32 bytes')
        secret_values = {
            os.getenv('JWT_SECRET_KEY', '').strip(),
            os.getenv('TRANSPORT_CRYPTO_PRIVATE_KEY', '').strip(),
            os.getenv('TRANSPORT_CRYPTO_PUBLIC_KEY', '').strip(),
        }
        legacy_config = globals().get('JwtConfig')
        transport_config = globals().get('TransportCryptoConfig')
        if legacy_config is not None:
            secret_values.add(str(getattr(legacy_config, 'jwt_secret_key', '')).strip())
        if transport_config is not None:
            secret_values.add(str(getattr(transport_config, 'transport_crypto_private_key', '')).strip())
            secret_values.add(str(getattr(transport_config, 'transport_crypto_public_key', '')).strip())
        secret_values.add(self.oidc_signing_key_encryption_key.strip())
        if pepper in secret_values:
            raise ValueError('OIDC_TOKEN_HASH_PEPPER 不得复用 Legacy JWT 或传输加密密钥')
        # 运行时以数据库 active 密钥为唯一事实；密钥可来自数据库加密密文，
        # 因此不能在配置层强制 OIDC_ACTIVE_KID 或文件路径。

    def _validate_cookie(self) -> None:
        """
        校验认证中心 SSO Cookie 的固定安全属性。

        :raises ValueError: Cookie 名称、Secure、SameSite 或 Domain 不符合要求
        """
        if not self.oidc_sso_cookie_name.startswith('__Host-'):
            raise ValueError('OIDC_SSO_COOKIE_NAME 必须使用 __Host- 前缀')
        if not self.oidc_sso_cookie_secure:
            raise ValueError('OIDC_SSO_COOKIE_SECURE 启用认证中心时必须为 true')
        if self.oidc_sso_cookie_domain:
            raise ValueError('__Host- SSO Cookie 不得设置 Domain')
        if self.oidc_sso_cookie_samesite != 'lax':
            raise ValueError('OIDC_SSO_COOKIE_SAMESITE 必须为 lax')

    def _validate_interaction_urls(self) -> None:
        """
        校验认证交互 URL 与 issuer 的同源约束。

        :raises ValueError: 交互地址不是 HTTPS 同源地址
        """
        issuer = urlsplit(self.oidc_issuer)
        for field_name, value in (
            ('OIDC_INTERACTION_LOGIN_URL', self.oidc_interaction_login_url),
            ('OIDC_INTERACTION_CONSENT_URL', self.oidc_interaction_consent_url),
            ('OIDC_INTERACTION_ERROR_URL', self.oidc_interaction_error_url),
        ):
            normalised = self._normalise_url(value, field_name)
            parsed = urlsplit(normalised)
            if (parsed.scheme, parsed.hostname, parsed.port) != (issuer.scheme, issuer.hostname, issuer.port):
                raise ValueError(f'{field_name} 必须与 OIDC_ISSUER 同 scheme、host、port')
            setattr(self, field_name.lower(), normalised)

    def _validate_cors_origins(self, app_env: str) -> None:
        """
        校验显式 CORS Origin 配置。

        :param app_env: 当前应用环境
        :raises ValueError: Origin 含 userinfo、path、query、fragment 或协议不安全
        """
        for origin in self.cors_origin_list:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {'http', 'https'}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError('OIDC_CORS_ALLOWED_ORIGINS 必须为 scheme + host + port Origin')
            if parsed.scheme != 'https' and not (app_env in {'dev', 'test', 'local'} and self._is_local_http(origin)):
                raise ValueError('生产环境 OIDC_CORS_ALLOWED_ORIGINS 必须使用 HTTPS')

    @model_validator(mode='after')
    def validate_oidc_configuration(self) -> 'OidcSettings':
        """
        执行 OIDC 启动级安全校验。

        :return: 已完成规范化和安全校验的配置对象
        """
        self.oidc_issuer = self._normalise_url(self.oidc_issuer, 'OIDC_ISSUER', allow_empty=not self.oidc_enabled)
        self.oidc_public_base_url = self._normalise_url(
            self.oidc_public_base_url,
            'OIDC_PUBLIC_BASE_URL',
            allow_empty=not self.oidc_enabled,
        )
        if not self.oidc_enabled:
            return self

        app_env = os.getenv('APP_ENV', 'dev').strip().strip('\'"').lower() or 'dev'
        self._validate_issuer_urls(app_env)
        self._validate_protocol_options()
        self._validate_secret_material()
        self._validate_cookie()
        self._validate_interaction_urls()
        self._validate_cors_origins(app_env)
        return self


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

    def get_oidc_config(self) -> OidcSettings:
        """
        获取统一认证中心配置。

        OIDC 配置由模型自身执行启动级校验；关闭时不会校验密钥和 Pepper。
        """
        return OidcSettings()

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
# 统一认证中心配置
OidcConfig = get_config.get_oidc_config()
# 插件依赖安装策略配置
PluginDependencyPolicyConfig = get_config.get_plugin_dependency_policy_config()
# 代码生成配置
GenConfig = get_config.get_gen_config()
# 上传配置
UploadConfig = get_config.get_upload_config()
