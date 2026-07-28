import re
from dataclasses import dataclass
from itertools import zip_longest

VERSION_PATTERN = re.compile(
    r'^v?(?P<release>\d+(?:\.\d+)*)(?:[-_\.]?(?P<prerelease>a|alpha|b|beta|rc|dev|pre|preview)(?P<prenum>\d*)?)?(?:\+.*)?$',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PluginVersion:
    """
    插件版本值对象。

    使用 Value Object 模式封装插件版本解析和比较所需的结构化信息。
    """

    raw: str
    release: tuple[int, ...]
    prerelease_label: str | None = None
    prerelease_number: int = 0

    @property
    def is_prerelease(self) -> bool:
        """
        判断版本是否为预发布版本。

        :return: 是否为预发布版本
        """
        return self.prerelease_label is not None


class PluginVersionParser:
    """
    插件版本解析器。

    使用 Parser 模式将常见语义版本字符串解析为可比较的版本值对象。
    """

    @classmethod
    def parse(cls, version: str | None) -> PluginVersion | None:
        """
        解析插件版本。

        :param version: 插件版本字符串
        :return: 插件版本值对象，非标准版本返回 None
        """
        if not version:
            return None
        matched_version = VERSION_PATTERN.match(version.strip())
        if not matched_version:
            return None
        release = tuple(int(part) for part in matched_version.group('release').split('.'))
        prerelease_label = cls.normalize_prerelease_label(matched_version.group('prerelease'))
        prerelease_number_text = matched_version.group('prenum') or '0'

        return PluginVersion(
            raw=version,
            release=release,
            prerelease_label=prerelease_label,
            prerelease_number=int(prerelease_number_text),
        )

    @staticmethod
    def normalize_prerelease_label(label: str | None) -> str | None:
        """
        规范化预发布标识。

        :param label: 原始预发布标识
        :return: 规范化后的预发布标识
        """
        if label is None:
            return None
        label_map = {
            'a': 'alpha',
            'b': 'beta',
            'pre': 'preview',
        }

        return label_map.get(label.lower(), label.lower())


class PluginVersionComparator:
    """
    插件版本比较器。

    使用 Comparator 模式提供插件版本相等、排序和升级判断能力。
    """

    PRERELEASE_ORDER = {
        'dev': 0,
        'alpha': 1,
        'beta': 2,
        'preview': 3,
        'rc': 4,
    }

    @classmethod
    def compare(cls, left: str | None, right: str | None) -> int | None:
        """
        比较两个插件版本。

        :param left: 左侧版本
        :param right: 右侧版本
        :return: 左侧大于右侧返回 1，等于返回 0，小于返回 -1，无法解析返回 None
        """
        left_version = PluginVersionParser.parse(left)
        right_version = PluginVersionParser.parse(right)
        if left_version is None or right_version is None:
            return None

        release_comparison = cls.compare_release(left_version.release, right_version.release)
        if release_comparison != 0:
            return release_comparison

        return cls.compare_prerelease(left_version, right_version)

    @staticmethod
    def compare_release(left: tuple[int, ...], right: tuple[int, ...]) -> int:
        """
        比较版本发布号。

        :param left: 左侧发布号
        :param right: 右侧发布号
        :return: 左侧大于右侧返回 1，等于返回 0，小于返回 -1
        """
        for left_part, right_part in zip_longest(left, right, fillvalue=0):
            if left_part > right_part:
                return 1
            if left_part < right_part:
                return -1

        return 0

    @classmethod
    def compare_prerelease(cls, left: PluginVersion, right: PluginVersion) -> int:
        """
        比较版本预发布号。

        :param left: 左侧版本
        :param right: 右侧版本
        :return: 左侧大于右侧返回 1，等于返回 0，小于返回 -1
        """
        if not left.is_prerelease and not right.is_prerelease:
            return 0
        if not left.is_prerelease:
            return 1
        if not right.is_prerelease:
            return -1
        left_label_order = cls.PRERELEASE_ORDER.get(left.prerelease_label or '', -1)
        right_label_order = cls.PRERELEASE_ORDER.get(right.prerelease_label or '', -1)
        if left_label_order != right_label_order:
            return 1 if left_label_order > right_label_order else -1
        if left.prerelease_number == right.prerelease_number:
            return 0

        return 1 if left.prerelease_number > right.prerelease_number else -1

    @classmethod
    def equals(cls, left: str | None, right: str | None) -> bool:
        """
        判断两个插件版本是否等价。

        :param left: 左侧版本
        :param right: 右侧版本
        :return: 是否等价
        """
        comparison = cls.compare(left, right)
        if comparison is None:
            return (left or '') == (right or '')

        return comparison == 0

    @classmethod
    def is_upgrade_available(cls, installed_version: str | None, source_version: str | None) -> bool:
        """
        判断源码版本是否高于已安装版本。

        :param installed_version: 已安装版本
        :param source_version: 源码版本
        :return: 是否存在可升级版本
        """
        if not installed_version or not source_version:
            return False
        comparison = cls.compare(source_version, installed_version)
        if comparison is None:
            return source_version != installed_version

        return comparison > 0


class PluginVersionConstraintMatcher:
    """
    插件版本约束匹配器。

    使用 Matcher 模式匹配插件版本与版本约束。
    """

    @classmethod
    def is_satisfied(cls, version: str | None, operator: str | None, required_version: str | None) -> bool:
        """
        判断插件版本是否满足约束。

        :param version: 插件版本
        :param operator: 版本操作符
        :param required_version: 约束版本
        :return: 是否满足
        """
        if not version:
            return False
        if not operator or not required_version:
            return True
        if operator in {'^', '~'}:
            return cls.match_compatible(version, required_version, operator)

        comparison = PluginVersionComparator.compare(version, required_version)
        if comparison is None:
            return cls.match_text_version(version, operator, required_version)

        operator_matchers = {
            '==': comparison == 0,
            '=': comparison == 0,
            '>=': comparison >= 0,
            '<=': comparison <= 0,
            '>': comparison > 0,
            '<': comparison < 0,
            '!=': comparison != 0,
        }

        return operator_matchers.get(operator, False)

    @classmethod
    def match_compatible(cls, version: str, required_version: str, operator: str) -> bool:
        """
        匹配兼容版本约束。

        :param version: 插件版本
        :param required_version: 约束版本
        :param operator: 兼容版本操作符
        :return: 是否满足兼容约束
        """
        parsed_version = PluginVersionParser.parse(version)
        parsed_required_version = PluginVersionParser.parse(required_version)
        if parsed_version is None or parsed_required_version is None:
            return version == required_version or version.startswith(f'{required_version}.')
        if PluginVersionComparator.compare(version, required_version) == -1:
            return False
        if operator == '~':
            return cls._release_prefix(parsed_version.release, 2) == cls._release_prefix(
                parsed_required_version.release,
                2,
            )

        return cls._major(parsed_version.release) == cls._major(parsed_required_version.release)

    @staticmethod
    def match_text_version(version: str, operator: str, required_version: str) -> bool:
        """
        匹配非标准文本版本。

        :param version: 插件版本
        :param operator: 版本操作符
        :param required_version: 约束版本
        :return: 是否满足文本版本约束
        """
        if operator in {'==', '='}:
            return version == required_version
        if operator == '!=':
            return version != required_version

        return False

    @staticmethod
    def _major(release: tuple[int, ...]) -> int:
        """
        获取主版本号。

        :param release: 发布号
        :return: 主版本号
        """
        return release[0] if release else 0

    @staticmethod
    def _release_prefix(release: tuple[int, ...], length: int) -> tuple[int, ...]:
        """
        获取发布号前缀。

        :param release: 发布号
        :param length: 前缀长度
        :return: 发布号前缀
        """
        return tuple(release[index] if index < len(release) else 0 for index in range(length))
