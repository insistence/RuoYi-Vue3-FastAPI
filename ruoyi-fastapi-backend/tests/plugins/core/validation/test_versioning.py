from plugins.core.validation.versioning import (
    PluginVersionComparator,
    PluginVersionConstraintMatcher,
    PluginVersionParser,
)


def test_plugin_version_parser_parses_common_semantic_versions() -> None:
    """校验插件版本解析器支持常见语义版本格式。"""
    version = PluginVersionParser.parse('v1.2.3-rc1+build.5')

    assert version is not None
    assert version.release == (1, 2, 3)
    assert version.prerelease_label == 'rc'
    assert version.prerelease_number == 1


def test_plugin_version_comparator_compares_release_and_prerelease_versions() -> None:
    """校验插件版本比较器支持发布号和预发布号比较。"""
    assert PluginVersionComparator.compare('1.10.0', '1.2.0') == 1
    assert PluginVersionComparator.compare('1.0.0', '1.0') == 0
    assert PluginVersionComparator.compare('1.0.0', '1.0.0-rc1') == 1
    assert PluginVersionComparator.compare('1.0.0-beta2', '1.0.0-beta1') == 1


def test_plugin_version_comparator_detects_upgrade_only_when_source_is_newer() -> None:
    """校验插件版本比较器只在源码版本更高时标记升级。"""
    assert PluginVersionComparator.is_upgrade_available('1.2.0', '1.10.0') is True
    assert PluginVersionComparator.is_upgrade_available('1.10.0', '1.2.0') is False
    assert PluginVersionComparator.is_upgrade_available('1.0.0', '1.0.0') is False


def test_plugin_version_constraint_matcher_supports_common_operators() -> None:
    """校验插件版本约束匹配器支持常见操作符。"""
    assert PluginVersionConstraintMatcher.is_satisfied('1.10.0', '>=', '1.2.0') is True
    assert PluginVersionConstraintMatcher.is_satisfied('1.0.0-rc1', '<', '1.0.0') is True
    assert PluginVersionConstraintMatcher.is_satisfied('2.0.0', '^', '1.2.0') is False
    assert PluginVersionConstraintMatcher.is_satisfied('1.2.9', '~', '1.2.0') is True
