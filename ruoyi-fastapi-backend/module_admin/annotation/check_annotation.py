import re
from functools import wraps
from typing import Literal, Optional
from pydantic import (
    BaseModel,
    Field,
    AnyUrl,
    AnyHttpUrl,
    HttpUrl,
    AnyWebsocketUrl,
    WebsocketUrl,
    FileUrl,
    FtpUrl,
    PostgresDsn,
    CockroachDsn,
    AmqpDsn,
    RedisDsn,
    MongoDsn,
    KafkaDsn,
    NatsDsn,
    MySQLDsn,
    MariaDBDsn,
    ClickHouseDsn,
    EmailStr,
    NameEmail,
    IPvAnyAddress,
    ValidationError
)
from exceptions.exception import FieldValidatorException
from utils.string_util import StringUtil


class NetWorkAnnotationModel(BaseModel):
    any_url: Optional[AnyUrl] = Field(default=None, description='接受任何URL类型')
    any_http_url: Optional[AnyHttpUrl] = Field(default=None, description='接受任何http或https URL的类型')
    http_url: Optional[HttpUrl] = Field(default=None, description='接受任何最大长度2083 & http或https URL的类型')
    any_websocket_url: Optional[AnyWebsocketUrl] = Field(default=None, description='接受任何ws或wss URL的类型')
    websocket_url: Optional[WebsocketUrl] = Field(default=None, description='接受任何最大长度 2083 & ws或wss URL的类型')
    file_url: Optional[FileUrl] = Field(default=None, description='接受任何文件URL的类型')
    ftp_url: Optional[FtpUrl] = Field(default=None, description='接受ftp URL的类型')
    postgres_dsn: Optional[PostgresDsn] = Field(default=None, description='接受任何Postgres DSN的类型')
    cockroach_dsn: Optional[CockroachDsn] = Field(default=None, description='接受任何Cockroach DSN的类型')
    amqp_dsn: Optional[AmqpDsn] = Field(default=None, description='接受任何AMQP DSN的类型')
    redis_dsn: Optional[RedisDsn] = Field(default=None, description='接受任何Redis DSN的类型')
    mongo_dsn: Optional[MongoDsn] = Field(default=None, description='接受任何MongoDB DSN的类型')
    kafka_dsn: Optional[KafkaDsn] = Field(default=None, description='接受任何Kafka DSN的类型')
    nats_dsn: Optional[NatsDsn] = Field(default=None, description='接受任何NATS DSN的类型')
    mysql_dsn: Optional[MySQLDsn] = Field(default=None, description='接受任何MySQL DSN的类型')
    mariadb_dsn: Optional[MariaDBDsn] = Field(default=None, description='接受任何MariaDB DSN的类型')
    clickhouse_dsn: Optional[ClickHouseDsn] = Field(default=None, description='接受任何ClickHouse DSN的类型')
    email_str: Optional[EmailStr] = Field(default=None, description='验证电子邮件地址')
    name_email: Optional[NameEmail] = Field(default=None, description='验证RFC 5322指定的名称和电子邮件地址组合')
    ipv_any_address: Optional[IPvAnyAddress] = Field(default=None, description='验证IPv4或IPv6地址')


class ValidateFields:
    """
    字段校验装饰器
    """
    def __init__(self, validate_model: str, validate_function: str = 'validate_fields'):
        """
        字段校验装饰器
        :param validate_model: 需要校验的pydantic模型在函数中的名称
        :param validate_function: pydantic模型中定义的校验函数名称
        :return:
        """
        self.validate_model = validate_model
        self.validate_function = validate_function

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            check_model = kwargs.get(self.validate_model)
            if isinstance(check_model, BaseModel) and hasattr(check_model, self.validate_function):
                validate_function = getattr(check_model, self.validate_function, None)
                if validate_function is not None and callable(validate_function):
                    validate_function()
            return await func(*args, **kwargs)
        return wrapper


class NetWork:
    """
    字段网络类型校验装饰器
    """
    def __init__(
            self,
            field_name: str,
            field_type: Literal['AnyUrl', 'AnyHttpUrl', 'HttpUrl', 'AnyWebsocketUrl', 'WebsocketUrl', 'FileUrl',
                                'FtpUrl', 'PostgresDsn', 'CockroachDsn', 'AmqpDsn', 'RedisDsn', 'MongoDsn', 'KafkaDsn',
                                'NatsDsn', 'MySQLDsn', 'MariaDBDsn', 'ClickHouseDsn', 'EmailStr', 'NameEmail',
                                'IPvAnyAddress'],
            message: Optional[str] = None
    ):
        """
        字段网络类型校验装饰器
        :param field_name: 需要校验的字段名称
        :param field_type: 需要校验的字段类型
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.field_type = field_type
        self.message = message

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                try:
                    if self.field_type == 'AnyUrl':
                        NetWorkAnnotationModel(any_url=field_value)
                    elif self.field_type == 'AnyHttpUrl':
                        NetWorkAnnotationModel(any_http_url=field_value)
                    elif self.field_type == 'HttpUrl':
                        NetWorkAnnotationModel(http_url=field_value)
                    elif self.field_type == 'AnyWebsocketUrl':
                        NetWorkAnnotationModel(any_websocket_url=field_value)
                    elif self.field_type == 'WebsocketUrl':
                        NetWorkAnnotationModel(websocket_url=field_value)
                    elif self.field_type == 'FileUrl':
                        NetWorkAnnotationModel(file_url=field_value)
                    elif self.field_type == 'FtpUrl':
                        NetWorkAnnotationModel(ftp_url=field_value)
                    elif self.field_type == 'PostgresDsn':
                        NetWorkAnnotationModel(postgres_dsn=field_value)
                    elif self.field_type == 'CockroachDsn':
                        NetWorkAnnotationModel(cockroach_dsn=field_value)
                    elif self.field_type == 'AmqpDsn':
                        NetWorkAnnotationModel(amqp_dsn=field_value)
                    elif self.field_type == 'RedisDsn':
                        NetWorkAnnotationModel(redis_dsn=field_value)
                    elif self.field_type == 'MongoDsn':
                        NetWorkAnnotationModel(mongo_dsn=field_value)
                    elif self.field_type == 'KafkaDsn':
                        NetWorkAnnotationModel(kafka_dsn=field_value)
                    elif self.field_type == 'NatsDsn':
                        NetWorkAnnotationModel(nats_dsn=field_value)
                    elif self.field_type == 'MySQLDsn':
                        NetWorkAnnotationModel(mysql_dsn=field_value)
                    elif self.field_type == 'MariaDBDsn':
                        NetWorkAnnotationModel(mariadb_dsn=field_value)
                    elif self.field_type == 'ClickHouseDsn':
                        NetWorkAnnotationModel(clickhouse_dsn=field_value)
                    elif self.field_type == 'EmailStr':
                        NetWorkAnnotationModel(email_str=field_value)
                    elif self.field_type == 'NameEmail':
                        NetWorkAnnotationModel(name_email=field_value)
                    elif self.field_type == 'IPvAnyAddress':
                        NetWorkAnnotationModel(ipv_any_address=field_value)
                except (ValidationError, ValueError):
                    raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}不是正确的{self.field_type}类型')
            return func(*args, **kwargs)
        return wrapper


class NotBlank:
    """
    字段非空校验装饰器
    """
    def __init__(self, field_name: str, message: Optional[str] = None):
        """
        字段非空校验装饰器
        :param field_name: 需要校验的字段名称
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.message = message

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if field_value is None or field_value == '' or field_value == [] or field_value == () or field_value == {}:
                    raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}不能为空')
            return func(*args, **kwargs)
        return wrapper


class Pattern:
    """
    字段正则校验装饰器
    """
    def __init__(self, field_name: str, regexp: str, message: Optional[str] = None):
        """
        字段正则校验装饰器
        :param field_name: 需要校验的字段名称
        :param regexp: 正则表达式
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.regexp = regexp
        self.message = message

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if isinstance(field_value, str) and not re.match(self.regexp, field_value):
                    raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}格式不正确')
            return func(*args, **kwargs)
        return wrapper


class Size:
    """
    字段大小校验装饰器
    """
    def __init__(self, field_name: str, gt: Optional[float] = None, ge: Optional[float] = None,
                 lt: Optional[float] = None, le: Optional[float] = None, min_length: Optional[int] = 0,
                 max_length: Optional[int] = None, message: Optional[str] = None):
        """
        字段大小校验装饰器
        :param field_name: 需要校验的字段名称
        :param gt: 数字型字段值必须要大于gt
        :param ge: 数字型字段值必须要大于等于ge
        :param lt: 数字型字段值必须要小于ge
        :param le: 数字型字段值必须要小于等于ge
        :param min_length: 字符串型字段长度不能小于min_length
        :param max_length: 字符串型字段长度不能大于max_length
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.min_length = min_length if min_length >= 0 else 0
        self.max_length = max_length
        self.message = message

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if isinstance(field_value, float):
                    if self.gt is not None and field_value <= self.gt:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须大于{self.gt}')
                    elif self.ge is not None and field_value < self.ge:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须大于等于{self.ge}')
                    elif self.lt is not None and field_value >= self.lt:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须小于{self.lt}')
                    elif self.le is not None and field_value > self.le:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}必须小于等于{self.le}')
                elif isinstance(field_value, str):
                    if len(field_value) < self.min_length:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}长度不能小于{self.min_length}')
                    elif self.max_length is not None and len(field_value) > self.max_length:
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}长度不能大于{self.max_length}')
            return func(*args, **kwargs)
        return wrapper


class Xss:
    """
    字段Xss校验装饰器
    """
    HTML_PATTERN = '<(\S*?)[^>]*>.*?|<.*? />'

    def __init__(self, field_name: str, message: Optional[str] = None):
        """
        字段Xss校验装饰器
        :param field_name: 需要校验的字段名称
        :param message: 校验失败的提示信息
        :return:
        """
        self.field_name = field_name
        self.message = message

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            check_model = args[0]
            if isinstance(check_model, BaseModel):
                field_value = getattr(check_model, self.field_name)
                if not StringUtil.is_blank(field_value):
                    pattern = re.compile(self.HTML_PATTERN)
                    if pattern.search(field_value):
                        raise FieldValidatorException(message=self.message if self.message else f'{self.field_name}不能包含脚本字符')
            return func(*args, **kwargs)
        return wrapper
