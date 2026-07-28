from dataclasses import dataclass, field

from packaging.requirements import Requirement
from packaging.version import InvalidVersion


@dataclass(frozen=True)
class ParsedPythonRequirement:
    """
    已解析 PEP 508 Python 依赖声明。

    保留 packaging 的解析结果，供 manifest 校验、运行时检查和依赖安装策略
    共享同一套名称、版本范围和环境 marker 语义。
    """

    raw: str
    requirement: Requirement = field(repr=False)

    @property
    def name(self) -> str:
        """
        获取规范化包名。

        :return: Python 包名
        """
        return self.requirement.name

    @property
    def specifier(self) -> str | None:
        """
        获取版本约束。

        :return: PEP 440 版本约束
        """
        return str(self.requirement.specifier) if self.requirement.specifier else None

    @property
    def required_version(self) -> str | None:
        """
        获取完整版本约束。

        :return: PEP 440 版本约束
        """
        return self.specifier

    @property
    def marker(self) -> str | None:
        """
        获取环境 marker。

        :return: PEP 508 marker
        """
        return str(self.requirement.marker) if self.requirement.marker else None

    @property
    def url(self) -> str | None:
        """
        获取直接引用地址。

        :return: PEP 508 直接引用地址
        """
        return self.requirement.url

    def is_marker_applicable(self) -> bool:
        """
        判断依赖 marker 是否适用于当前环境。

        :return: 是否适用于当前环境
        """
        return self.requirement.marker is None or self.requirement.marker.evaluate()

    def is_version_satisfied(self, installed_version: str | None) -> bool:
        """
        判断已安装版本是否满足 PEP 440 约束。

        对无法解析或不满足约束的版本统一返回 False，避免依赖策略 fail-open。

        :param installed_version: 已安装或锁定版本
        :return: 是否满足版本约束
        """
        if not installed_version:
            return False
        if not self.requirement.specifier:
            return True
        try:
            return self.requirement.specifier.contains(installed_version)
        except InvalidVersion:
            return False


class PythonRequirementParser:
    """
    PEP 508 Python 依赖声明解析器。

    解析失败时保留 packaging 的 ``InvalidRequirement`` 异常，由 manifest 和
    运行时边界分别转换为明确的校验错误或失败结果。
    """

    @staticmethod
    def parse(requirement: str) -> ParsedPythonRequirement:
        """
        解析 PEP 508 Python 依赖声明。

        :param requirement: Python 依赖声明
        :return: 已解析 Python 依赖声明
        :raises InvalidRequirement: 依赖声明不符合 PEP 508
        """
        return ParsedPythonRequirement(raw=requirement, requirement=Requirement(requirement))
