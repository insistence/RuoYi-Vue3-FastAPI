import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from config.env import JwtConfig
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.sdk.config import PluginConfigSnapshot


def config_revision(plugin_id: str, values: Mapping[str, Any]) -> str:
    """
    生成绑定插件和宿主密钥的不透明版本，避免公开敏感配置的可枚举裸哈希。

    :param plugin_id: 当前插件标识
    :param values: 按清单合并默认值后的配置明文
    :return: 可比较但不可据此还原配置的 HMAC 摘要
    """
    payload = json.dumps(
        ['plugin-config-v1', plugin_id, dict(values)],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hmac.new(JwtConfig.jwt_secret_key.encode('utf-8'), payload, hashlib.sha256).hexdigest()


class PluginConfigObservation(BaseModel):
    """
    当前 worker 的启动配置和最近一次按需读取版本，不包含配置值。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid', strict=True)

    plugin_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,63}$')
    version: str = Field(max_length=128)
    digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    generation: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    active: bool = False
    startup_revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    last_read_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    last_read_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PluginConfigReader:
    """
    绑定已加载清单的配置读取器，每次读取使用自己的数据库会话。
    """

    def __init__(
        self,
        plugin: DiscoveredPlugin,
        session_factory: Callable[..., Any],
        observation: PluginConfigObservation,
    ) -> None:
        """
        固定插件身份，调用方不能提供其他插件 ID。

        :param plugin: 当前进程实际加载的插件
        :param session_factory: 宿主提供的数据库会话工厂
        :param observation: 不包含敏感值的运行观测记录
        :return: None
        """
        self.plugin = plugin
        self.session_factory = session_factory
        self.observation = observation

    async def read(self) -> PluginConfigSnapshot:
        """
        读取已提交配置并记录读取版本，数据库错误直接交由调用方处理。

        :return: 独立的插件配置快照，不代表业务代码已完成应用
        """
        from plugins.core.management.service.service import PluginService  # noqa: PLC0415

        async with self.session_factory() as db:
            configs = await PluginService.get_plugin_config_services(db, self.plugin, reveal_secret=True)
        values = {item.key: item.value for item in configs}
        snapshot = PluginConfigSnapshot(values, config_revision(self.plugin.manifest.id, values))
        self.observation.last_read_revision = snapshot.revision
        self.observation.last_read_at = time.time()
        return snapshot


def build_config_status(plugin_id: str, desired_revision: str, report: Mapping[str, Any]) -> dict[str, Any]:
    """
    比较已观测进程的启动快照，不把按需读取或局部观测当成全局生效。

    :param plugin_id: 当前插件标识
    :param desired_revision: 当前数据库配置版本
    :param report: 指标报告器返回的进程快照与范围信息
    :return: 包含待重启数量和明确采样范围的配置状态
    """
    workers = [
        {
            'workerId': worker['workerId'],
            'collectedAt': worker['collectedAt'],
            **config,
            'matchesDesired': config['active'] and config['startupRevision'] == desired_revision,
        }
        for worker in report.get('workers', [])
        for config in worker.get('configurations', [])
        if config['pluginId'] == plugin_id
    ]
    pending = sum(worker['active'] and not worker['matchesDesired'] for worker in workers)
    matched = sum(worker['matchesDesired'] for worker in workers)
    unknown = sum(
        any(series['pluginId'] == plugin_id for series in worker.get('series', []))
        and not any(config['pluginId'] == plugin_id for config in worker.get('configurations', []))
        for worker in report.get('workers', [])
    )
    return {
        'ok': True,
        'pluginId': plugin_id,
        'desiredRevision': desired_revision,
        'activationMode': 'startup_snapshot',
        'state': 'restart_required' if pending else 'observed_match' if matched else 'unobserved',
        'observedWorkers': len(workers),
        'matchedWorkers': matched,
        'pendingWorkers': pending,
        'unknownWorkers': unknown,
        'workers': workers,
        **{
            key: report.get(key)
            for key in (
                'scope',
                'currentWorkerId',
                'clusterAvailable',
                'sampleIntervalSeconds',
                'sampleTtlSeconds',
                'invalidSnapshots',
                'staleSnapshots',
                'workerLimitReached',
            )
        },
    }
