class PluginScaffoldNaming:
    """
    插件模板命名转换工具。
    """

    @staticmethod
    def to_class_name(plugin_id: str) -> str:
        """
        将插件 ID 转换为类名前缀。

        :param plugin_id: 插件ID
        :return: 类名前缀
        """
        return ''.join(part.capitalize() for part in plugin_id.replace('-', '_').split('_') if part)
