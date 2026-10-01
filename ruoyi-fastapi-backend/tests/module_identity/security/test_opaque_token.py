from collections.abc import Callable

import pytest

from module_identity.security.opaque_token import (
    OpaqueTokenError,
    generate_authorization_code,
    generate_refresh_token,
    generate_sso_cookie,
    parse_opaque_token,
    token_digest,
    verify_token_digest,
)


@pytest.mark.parametrize(
    ('factory', 'prefix'),
    ((generate_authorization_code, 'ac1'), (generate_refresh_token, 'rt1'), (generate_sso_cookie, 'ss1')),
)
def test_typed_tokens_are_random_and_verifiable(factory: Callable[[], str], prefix: str) -> None:
    pepper = 'p' * 32
    token = factory()
    parsed = parse_opaque_token(token, expected_prefix=prefix)
    digest = token_digest(token, pepper)

    assert parsed.prefix == prefix
    assert verify_token_digest(token, digest, pepper)
    assert not verify_token_digest(token.replace(prefix, 'rt1' if prefix != 'rt1' else 'ac1', 1), digest, pepper)


def test_token_id_alone_is_not_a_credential() -> None:
    token = generate_refresh_token()
    parsed = parse_opaque_token(token)
    pepper = 'p' * 32
    digest = token_digest(token, pepper)

    assert not verify_token_digest(parsed.token_id, digest, pepper)
    with pytest.raises(OpaqueTokenError):
        parse_opaque_token('unknown.' + token.split('.', 1)[1])
    assert not verify_token_digest(token, digest, 'p' * 16)
    with pytest.raises(ValueError):
        token_digest(token, 'p' * 16)
