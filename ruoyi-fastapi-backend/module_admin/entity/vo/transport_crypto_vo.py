from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TransportCryptoFrontendConfigModel(BaseModel):
    """
    传输层加解密前端运行配置模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    transport_crypto_enabled: bool = Field(description='后端是否启用传输层加解密')
    transport_crypto_mode: str = Field(description='当前传输层加解密模式')
    transport_crypto_active: bool = Field(description='前端当前是否应启用传输层加解密')
    envelope_version: str = Field(description='当前传输层加密信封协议版本')
    public_key_url: str = Field(description='传输层公钥接口路径')
    request_envelope_algorithm: str = Field(description='前端请求信封算法标识')
    response_envelope_algorithm: str = Field(description='前端响应信封算法标识')
    enabled_paths: list[str] = Field(description='启用传输层加解密的路径列表')
    required_paths: list[str] = Field(description='强制要求加密传输的路径列表')
    exclude_paths: list[str] = Field(description='排除传输层加解密的路径列表')
    max_encrypted_get_url_length: int = Field(description='前端执行加密GET/DELETE请求时允许的最大URL长度')
    config_expire_at: int = Field(description='前端配置建议刷新时间戳')


class TransportCryptoPublicKeyModel(BaseModel):
    """
    传输层加解密公钥下发模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    kid: str = Field(description='当前启用的密钥版本标识')
    envelope_version: str = Field(description='当前传输层加密信封协议版本')
    alg: str = Field(description='当前传输层加密算法标识')
    public_key: str = Field(description='当前可用的传输层公钥')
    supported_kids: list[str] = Field(description='当前支持解密的密钥版本列表')
    expire_at: int = Field(description='当前公钥建议刷新时间戳')


class TransportCryptoKidStatModel(BaseModel):
    """
    传输层加解密按密钥版本统计模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    kid: str | None = Field(default=None, description='密钥版本标识')
    encrypted_requests: int | None = Field(default=0, description='加密请求次数')
    decrypt_success: int | None = Field(default=0, description='请求解密成功次数')
    decrypt_failure: int | None = Field(default=0, description='请求解密失败次数')
    encrypted_responses: int | None = Field(default=0, description='加密响应次数')


class TransportCryptoFailureRecordModel(BaseModel):
    """
    传输层加解密最近失败记录模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    time: datetime | None = Field(default=None, description='失败时间')
    method: str | None = Field(default=None, description='请求方法')
    path: str | None = Field(default=None, description='请求路径')
    reason: str | None = Field(default=None, description='失败原因分类')
    kid: str | None = Field(default=None, description='密钥版本标识')


class TransportCryptoMonitorModel(BaseModel):
    """
    传输层加解密监控模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    monitor_scope: str | None = Field(default=None, description='监控统计范围，默认基于Redis聚合')
    started_at: datetime | None = Field(default=None, description='当前监控统计起始时间')
    app_env: str | None = Field(default=None, description='当前应用环境')
    transport_crypto_enabled: bool | None = Field(default=None, description='是否启用传输层加解密')
    transport_crypto_mode: str | None = Field(default=None, description='当前传输层加解密模式')
    current_kid: str | None = Field(default=None, description='当前启用的密钥版本')
    supported_kids: list[str] | None = Field(default=[], description='当前支持的密钥版本列表')
    enabled_paths: list[str] | None = Field(default=[], description='启用传输层加解密的路径列表')
    required_paths: list[str] | None = Field(default=[], description='强制要求加密传输的路径列表')
    exclude_paths: list[str] | None = Field(default=[], description='排除传输层加解密的路径列表')
    requests_total: int | None = Field(default=0, description='命中传输层加解密规则的请求总数')
    plain_requests_total: int | None = Field(default=0, description='明文请求总数')
    encrypted_requests_total: int | None = Field(default=0, description='加密请求总数')
    required_rejected_total: int | None = Field(default=0, description='强制加密接口被拒绝的次数')
    decrypt_success_total: int | None = Field(default=0, description='请求解密成功次数')
    decrypt_failure_total: int | None = Field(default=0, description='请求解密失败次数')
    plain_responses_total: int | None = Field(default=0, description='明文响应次数')
    encrypted_responses_total: int | None = Field(default=0, description='加密响应次数')
    encrypted_error_responses_total: int | None = Field(default=0, description='加密错误响应次数')
    failure_reasons: dict[str, int] | None = Field(default={}, description='按失败原因归类的次数统计')
    kid_stats: list[TransportCryptoKidStatModel] | None = Field(default=[], description='按密钥版本归类的统计信息')
    recent_failures: list[TransportCryptoFailureRecordModel] | None = Field(default=[], description='最近失败事件列表')
