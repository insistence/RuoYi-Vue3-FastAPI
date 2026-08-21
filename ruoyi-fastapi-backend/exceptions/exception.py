class LoginException(Exception):
    """
    自定义登录异常LoginException
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class AuthException(Exception):
    """
    自定义令牌异常AuthException
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class PermissionException(Exception):
    """
    自定义权限异常PermissionException
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class ServiceException(Exception):
    """
    自定义服务异常ServiceException
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class ServiceWarning(Exception):
    """
    自定义服务警告ServiceWarning
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class FileRangeNotSatisfiableException(Exception):
    """
    文件Range范围不可满足异常
    """

    def __init__(self, file_size: int) -> None:
        self.file_size = file_size


class ModelValidatorException(Exception):
    """
    自定义模型校验异常ModelValidatorException
    """

    def __init__(self, data: str | None = None, message: str | None = None) -> None:
        self.data = data
        self.message = message


class DataSourceException(ServiceException):
    """
    自定义数据源异常DataSourceException

    对外异常信息仅包含数据源名称，内部诊断字段仅保留异常类型和数字错误码。
    """

    def __init__(
        self,
        source_name: str,
        message: str | None = None,
        *,
        error_type: str | None = None,
        error_code: int | None = None,
    ) -> None:
        self.source_name = source_name
        self.error_type = error_type
        self.error_code = error_code
        super().__init__(message=message or f'数据源异常：{source_name}')


class DataSourceNotFoundException(DataSourceException):
    """
    自定义数据源未配置异常DataSourceNotFoundException
    """

    def __init__(self, source_name: str) -> None:
        super().__init__(source_name, message=f'数据源未配置：{source_name}')


class DataSourceUnavailableException(DataSourceException):
    """
    自定义数据源不可用异常DataSourceUnavailableException
    """

    def __init__(
        self,
        source_name: str,
        *,
        error_type: str | None = None,
        error_code: int | None = None,
    ) -> None:
        super().__init__(
            source_name,
            message=f'数据源暂不可用：{source_name}',
            error_type=error_type,
            error_code=error_code,
        )


class DataSourceInitializationException(DataSourceException):
    """
    自定义数据源初始化异常DataSourceInitializationException
    """

    def __init__(
        self,
        source_name: str,
        *,
        error_type: str | None = None,
        error_code: int | None = None,
    ) -> None:
        super().__init__(
            source_name,
            message=f'数据源初始化失败：{source_name}',
            error_type=error_type,
            error_code=error_code,
        )
