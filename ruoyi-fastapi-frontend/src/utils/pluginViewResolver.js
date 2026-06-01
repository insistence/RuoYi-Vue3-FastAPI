/**
 * 将后端菜单中的插件组件路径转换为 Vite glob key。
 * @param {string} view 后端返回的组件路径，格式为 plugin/<pluginId>/<viewPath>。
 * @returns {string} 插件视图在 Vite glob 模块表中的匹配路径。
 */
export const resolvePluginViewPath = (view) => {
  const parts = view.split('/').filter(Boolean)
  if (parts.length < 3 || parts[0] !== 'plugin') {
    return ''
  }

  const pluginId = parts[1]
  const viewPath = parts.slice(2).join('/')
  return `../../../plugins/${pluginId}/views/${viewPath}.vue`
}
