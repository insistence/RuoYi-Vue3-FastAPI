from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OidcUserPrincipal:
    """
    OIDC 用户主体，不承载可变数据库 user_id
    """

    subject_id: str
    client_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    audience: tuple[str, ...] = ()
    sid: str | None = None
    auth_version: int | None = None

    @property
    def sub(self) -> str:
        """
        返回稳定的 OIDC Subject

        :return: OIDC Subject
        """

        return self.subject_id


@dataclass(frozen=True, slots=True)
class OAuthClientPrincipal:
    """
    已完成 Client Authentication 的外部应用主体
    """

    client_id: str
    client_type: str
    auth_method: str | None = None


@dataclass(frozen=True, slots=True)
class MachinePrincipal:
    """
    明确的 client_credentials 身份，绝不伪装为用户
    """

    client_id: str
    subject: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    audience: tuple[str, ...] = ()

    @property
    def is_machine(self) -> bool:
        """
        标识该主体来自 client_credentials 机器身份

        :return: 固定返回 True
        """

        return True
