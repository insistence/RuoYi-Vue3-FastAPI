from datetime import datetime, timezone
from typing import Any

from cli.exit_codes import RUNTIME_ERROR

from .gateway import OidcInfrastructureGateway


class OidcRuntimeCliService:
    """
    OIDC CLI 运行时服务

    该服务对外统一暴露 OIDC 就绪检查和首把签名密钥初始化入口。

    :param infrastructure_gateway: OIDC 基础设施网关
    """

    def __init__(self, infrastructure_gateway: OidcInfrastructureGateway | None = None) -> None:
        """
        初始化 OIDC CLI 运行时服务

        :param infrastructure_gateway: OIDC 基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or OidcInfrastructureGateway()

    async def check_readiness(self) -> dict[str, Any]:
        """
        检查部署配置中的 OIDC 是否已具备签名能力

        :return: OIDC 就绪检查结果
        """
        data_source_registry = self.infrastructure_gateway.get_data_source_registry()
        oidc_config = self.infrastructure_gateway.get_oidc_config()
        runtime_service = self.infrastructure_gateway.get_runtime_service()

        if not oidc_config.oidc_enabled:
            return {
                'ok': True,
                'message': 'OIDC 未启用',
                'enabled': False,
                'ready': False,
                'reason': 'disabled',
            }
        try:
            await data_source_registry.initialize(log_enabled=False)
            async with data_source_registry.session() as db:
                readiness = await runtime_service.inspect_readiness(db)
            result = {
                'ok': readiness.ready,
                'message': 'OIDC 已就绪' if readiness.ready else 'OIDC 尚未初始化可用签名密钥',
                'enabled': readiness.enabled,
                'ready': readiness.ready,
                'reason': readiness.reason,
            }
            if not readiness.ready:
                result['error'] = readiness.reason
            return result
        except Exception as exc:
            return {
                'ok': False,
                'message': 'OIDC 就绪检查失败',
                'enabled': True,
                'ready': False,
                'reason': 'check_failed',
                'error': str(exc),
            }
        finally:
            await data_source_registry.dispose_all()

    async def bootstrap_signing_key(
        self,
        kid: str,
        *,
        actor: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        幂等创建并激活首把 OIDC 签名密钥

        :param kid: 首把签名密钥标识
        :param actor: 部署操作人标识
        :param dry_run: 是否只生成预演结果
        :return: OIDC 签名密钥初始化结果
        """
        if dry_run:
            return {
                'ok': True,
                'message': 'OIDC 签名密钥初始化预演完成，未写入数据库',
                'kid': kid,
                'created': False,
                'active': False,
                'dryRun': True,
            }

        data_source_registry = self.infrastructure_gateway.get_data_source_registry()
        redis_util = self.infrastructure_gateway.get_redis_util()
        key_management_service = self.infrastructure_gateway.get_key_management_service()

        redis = None
        try:
            await data_source_registry.initialize(log_enabled=False)
            redis = await redis_util.create_redis_pool(log_enabled=False)
            async with data_source_registry.session() as db:
                row, created = await key_management_service.bootstrap(
                    db,
                    kid=kid,
                    actor=actor,
                    redis=redis,
                    now=datetime.now(timezone.utc),
                )
            return {
                'ok': True,
                'message': 'OIDC 首把签名密钥已初始化' if created else 'OIDC 已存在可用签名密钥',
                'kid': row['kid'],
                'created': created,
                'active': row['status'] == 'active',
                'dryRun': False,
            }
        except Exception as exc:
            return {
                'ok': False,
                'message': 'OIDC 签名密钥初始化失败',
                'error': str(exc),
                'exit_code': RUNTIME_ERROR,
            }
        finally:
            if redis is not None:
                await redis.close()
            await data_source_registry.dispose_all()


OIDC_RUNTIME = OidcRuntimeCliService()
