import json
from types import SimpleNamespace

from cli.exit_codes import ARGUMENT_ERROR
from cli.runtime.crypto import CryptoRuntimeService
from cli.runtime.crypto.gateway import CryptoInfrastructureGateway
from cli.runtime.crypto.support import CryptoDomainSupport

INVALID_RSA_KEY_SIZE = 1024
VALID_RSA_KEY_SIZE = 2048


def test_crypto_domain_support_rejects_invalid_rsa_key_size() -> None:
    """
    校验传输加密领域支持对象会拒绝非法 RSA 密钥长度。

    :return: None
    """
    support = CryptoDomainSupport(CryptoInfrastructureGateway())

    try:
        support.validate_rsa_key_size(INVALID_RSA_KEY_SIZE)
    except ValueError as exc:
        assert 'RSA 密钥长度必须大于等于 2048' in str(exc)
    else:
        raise AssertionError('expected ValueError for invalid RSA key size')


def test_crypto_domain_support_rejects_non_list_legacy_key_pairs() -> None:
    """
    校验传输加密领域支持对象会拒绝非数组格式的历史密钥配置。

    :return: None
    """
    gateway = CryptoInfrastructureGateway()
    support = CryptoDomainSupport(gateway)

    def _fake_transport_crypto_config() -> SimpleNamespace:
        return SimpleNamespace(transport_crypto_legacy_key_pairs='{"kid": "legacy"}')

    object.__setattr__(gateway, 'get_transport_crypto_config', _fake_transport_crypto_config)

    try:
        support.load_existing_legacy_key_pairs()
    except ValueError as exc:
        assert 'TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS 必须为 JSON 数组' in str(exc)
    else:
        raise AssertionError('expected ValueError for invalid legacy key pairs payload')


def test_crypto_runtime_service_keygen_returns_argument_error_for_invalid_size() -> None:
    """
    校验传输加密运行时在非法密钥长度下返回参数错误结果。

    :return: None
    """
    service = CryptoRuntimeService()

    payload = service.generate_crypto_key_pair('kid-20260511', INVALID_RSA_KEY_SIZE)

    assert payload['ok'] is False
    assert payload['exit_code'] == ARGUMENT_ERROR
    assert payload['message'] == '生成传输加密密钥失败'


def test_crypto_runtime_service_rotation_rejects_same_kid() -> None:
    """
    校验传输加密运行时会拒绝与当前版本相同的新密钥版本。

    :return: None
    """
    gateway = CryptoInfrastructureGateway()
    service = CryptoRuntimeService(infrastructure_gateway=gateway)

    provider = SimpleNamespace(
        validate_runtime_configuration=lambda: None,
        get_current_key_pair=lambda: SimpleNamespace(
            kid='kid-current',
            private_key_pem='PRIVATE-CURRENT',
            public_key_pem='PUBLIC-CURRENT',
        ),
    )

    object.__setattr__(gateway, 'get_transport_key_provider', lambda: provider)

    payload = service.build_rotation_payload('kid-current', VALID_RSA_KEY_SIZE)

    assert payload['ok'] is False
    assert payload['exit_code'] == ARGUMENT_ERROR
    assert payload['message'] == '生成密钥轮换方案失败'
    assert payload['error'] == '新密钥版本不能与当前版本相同'


def test_crypto_runtime_service_rotation_builds_merged_payload() -> None:
    """
    校验传输加密运行时会生成包含历史密钥合并结果的轮换辅助数据。

    :return: None
    """
    gateway = CryptoInfrastructureGateway()
    domain_support = CryptoDomainSupport(gateway)
    service = CryptoRuntimeService(
        infrastructure_gateway=gateway,
        domain_support=domain_support,
    )
    provider = SimpleNamespace(
        validate_runtime_configuration=lambda: None,
        get_current_key_pair=lambda: SimpleNamespace(
            kid='kid-current',
            private_key_pem='PRIVATE-CURRENT',
            public_key_pem='PUBLIC-CURRENT',
        ),
    )

    object.__setattr__(gateway, 'get_transport_key_provider', lambda: provider)
    object.__setattr__(
        domain_support,
        'generate_rsa_key_pair',
        lambda key_size: ('PRIVATE-NEXT', 'PUBLIC-NEXT'),
    )
    object.__setattr__(
        domain_support,
        'load_existing_legacy_key_pairs',
        lambda: [
            {'kid': 'kid-legacy', 'privateKey': 'PRIVATE-LEGACY', 'publicKey': 'PUBLIC-LEGACY'},
            {'kid': 'kid-next', 'privateKey': 'STALE-PRIVATE', 'publicKey': 'STALE-PUBLIC'},
        ],
    )

    payload = service.build_rotation_payload('kid-next', VALID_RSA_KEY_SIZE)

    assert payload['ok'] is True
    assert payload['currentKid'] == 'kid-current'
    assert payload['nextKid'] == 'kid-next'
    assert payload['nextKeyPair']['privateKey'] == 'PRIVATE-NEXT'
    assert payload['nextKeyPair']['publicKey'] == 'PUBLIC-NEXT'
    assert payload['envPatch']['TRANSPORT_CRYPTO_KID'] == 'kid-next'
    assert payload['envPatch']['TRANSPORT_CRYPTO_PRIVATE_KEY'] == 'PRIVATE-NEXT'
    assert payload['envPatch']['TRANSPORT_CRYPTO_PUBLIC_KEY'] == 'PUBLIC-NEXT'

    legacy_key_pairs = payload['legacyKeyPairs']
    legacy_by_kid = {item['kid']: item for item in legacy_key_pairs}
    assert 'kid-next' not in legacy_by_kid
    assert legacy_by_kid['kid-current']['privateKey'] == 'PRIVATE-CURRENT'
    assert legacy_by_kid['kid-legacy']['publicKey'] == 'PUBLIC-LEGACY'

    serialized_legacy = json.loads(payload['envPatch']['TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS'])
    serialized_by_kid = {item['kid']: item for item in serialized_legacy}
    assert serialized_by_kid['kid-current']['publicKey'] == 'PUBLIC-CURRENT'
