from utils.oidc_util import OidcUtil


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


class OAuthProtocolException(Exception):
    """
    OAuth/OIDC 协议异常。

    异常 message 和字符串表示使用中文，error_description 保持 OAuth 要求的 ASCII 格式。
    统一异常处理器仅返回标准协议字段和经过验证的重定向状态，不回传内部诊断详情。
    """

    _DEFAULT_BAD_REQUEST_STATUS = 400

    def __init__(
        self,
        error: str,
        error_description: str | None = None,
        status_code: int = 400,
        *,
        redirect_uri: str | None = None,
        state: str | None = None,
        redirect_uri_verified: bool = False,
        issuer: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.error = error
        self.error_description = OidcUtil.protocol_error_description(error, error_description)
        self.message = OidcUtil.localized_oauth_message(error, error_description)
        self.status_code = (
            401 if error == 'invalid_client' and status_code == self._DEFAULT_BAD_REQUEST_STATUS else status_code
        )
        self.redirect_uri = redirect_uri
        self.state = state
        self.redirect_uri_verified = redirect_uri_verified
        self.issuer = issuer
        self.headers = dict(headers or {})
        super().__init__(self.message)

    @property
    def can_redirect(self) -> bool:
        """
        判断是否允许协议错误重定向。

        :return: Redirect URI 存在且已完成服务端精确校验时为 True
        """
        return bool(self.redirect_uri and self.redirect_uri_verified)

    @property
    def redirect_safe(self) -> bool:
        """
        返回安全重定向状态别名。

        :return: 与 :attr:`can_redirect` 相同的安全状态
        """
        return self.can_redirect

    def as_dict(self, *, include_state: bool = False) -> dict[str, str]:
        """
        转换为 OAuth 标准错误 JSON 字段。

        :param include_state: 是否在错误 JSON 中包含 state
        :return: 标准 OAuth 错误字段
        """
        result: dict[str, str] = {'error': self.error}
        if self.error_description:
            result['error_description'] = self.error_description
        if include_state and self.state:
            result['state'] = self.state
        return result


class OidcInteractionException(Exception):
    """
    认证交互状态异常。

    交互异常不默认跳转到外部地址；只有 Interaction 已绑定并验证了 Client
    Redirect URI 时，调用方才可将其转换为 ``OAuthProtocolException``。
    """

    def __init__(
        self,
        interaction_id: str | None = None,
        message: str | None = None,
        *,
        error: str = 'interaction_required',
        status_code: int = 400,
        redirect_uri: str | None = None,
        state: str | None = None,
        redirect_uri_verified: bool = False,
    ) -> None:
        self.interaction_id = interaction_id
        self.message = message or '认证交互无效或已过期'
        self.error = error
        self.status_code = status_code
        self.redirect_uri = redirect_uri
        self.state = state
        self.redirect_uri_verified = redirect_uri_verified
        super().__init__(self.message)

    @property
    def can_redirect(self) -> bool:
        """
        判断交互是否已经具备安全重定向条件。

        :return: 交互已绑定并验证 Client Redirect URI 时为 True
        """
        return bool(self.redirect_uri and self.redirect_uri_verified)

    def as_protocol_exception(self) -> OAuthProtocolException:
        """
        显式转换为标准 OAuth 协议异常。

        :return: 可由协议控制器处理的 OAuth 异常
        """
        return OAuthProtocolException(
            self.error,
            self.message,
            self.status_code,
            redirect_uri=self.redirect_uri,
            state=self.state,
            redirect_uri_verified=self.redirect_uri_verified,
        )


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
