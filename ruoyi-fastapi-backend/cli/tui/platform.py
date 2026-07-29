import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class TuiPlatformPolicy:
    """
    TUI 平台渲染策略。

    Windows 终端默认关闭持续动画，避免高频全行重绘与业务查询同时争用
    事件循环。可通过 ``RUOYI_TUI_REDUCED_MOTION`` 显式覆盖。
    """

    reduced_motion: bool

    @classmethod
    def detect(cls) -> 'TuiPlatformPolicy':
        """根据平台与显式环境变量构建渲染策略。"""
        override = os.environ.get('RUOYI_TUI_REDUCED_MOTION', '').strip().lower()
        if override in {'1', 'true', 'yes', 'on'}:
            return cls(reduced_motion=True)
        if override in {'0', 'false', 'no', 'off'}:
            return cls(reduced_motion=False)
        return cls(reduced_motion=sys.platform == 'win32')


TUI_PLATFORM_POLICY = TuiPlatformPolicy.detect()
