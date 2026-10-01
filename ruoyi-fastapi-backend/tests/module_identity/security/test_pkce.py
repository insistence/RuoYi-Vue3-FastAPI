import pytest

from module_identity.security.pkce import (
    PkceError,
    generate_code_challenge,
    generate_code_verifier,
    verify_code_challenge,
)

_VERIFIER_LENGTH = 64
_CHALLENGE_LENGTH = 43


def test_s256_round_trip_and_mismatch() -> None:
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)

    assert len(verifier) == _VERIFIER_LENGTH
    assert len(challenge) == _CHALLENGE_LENGTH
    assert verify_code_challenge(verifier, challenge)
    assert not verify_code_challenge(f'{verifier}a', challenge)


def test_plain_and_invalid_lengths_are_rejected() -> None:
    with pytest.raises(PkceError):
        verify_code_challenge('a' * 43, 'a' * 43, method='plain')
    with pytest.raises(ValueError):
        generate_code_verifier(42)
    with pytest.raises(PkceError):
        generate_code_challenge('a' * 42)
    assert not verify_code_challenge('a' * 43, '!' * 43)
