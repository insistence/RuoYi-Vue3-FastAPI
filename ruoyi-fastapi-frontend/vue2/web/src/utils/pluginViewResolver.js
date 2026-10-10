const PLUGIN_ID_PATTERN = /^[a-z][a-z0-9_-]{1,63}$/
const VIEW_SEGMENT_PATTERN = /^[a-z][a-z0-9_-]*$/

/**
 * 将后端菜单中的插件组件路径转换为 Webpack require.context key。
 * @param {string} view 后端返回的组件路径，格式为 plugin/<pluginId>/<viewPath>。
 * @returns {string} 插件视图在 Webpack 上下文中的匹配路径。
 */
const resolvePluginViewPath = (view) => {
  if (typeof view !== 'string') {
    return ''
  }

  const parts = view.replace(/^\/+/, '').split('/')
  if (parts.length < 3 || parts[0] !== 'plugin') {
    return ''
  }

  const pluginId = parts[1]
  const viewSegments = parts.slice(2)
  if (
    !PLUGIN_ID_PATTERN.test(pluginId) ||
    !viewSegments.every((segment) => VIEW_SEGMENT_PATTERN.test(segment))
  ) {
    return ''
  }

  return `./${pluginId}/views/${viewSegments.join('/')}.vue`
}

module.exports = {
  resolvePluginViewPath,
}
