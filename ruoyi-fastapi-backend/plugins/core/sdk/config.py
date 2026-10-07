from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class PluginConfigSnapshot:
    """
    一次读取的插件专属配置，版本用于判断是否需要重新应用业务设置。

    :param values: 当前插件的配置明文，只能在插件服务端使用
    :param revision: 宿主生成的不透明配置版本
    """

    values: Mapping[str, Any] = field(repr=False)
    revision: str

    def __post_init__(self) -> None:
        """
        深拷贝配置以隔离调用方修改，再保护顶层映射。

        :return: None
        """
        object.__setattr__(self, 'values', MappingProxyType(deepcopy(dict(self.values))))
