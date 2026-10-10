/**
 * 在认证页面加载前检查功能开关；错误说明页和普通页面不受影响。
 *
 * @param {Object} route 即将进入的路由
 * @param {Function} loadStatus 读取后端启用状态
 * @returns {Promise<Object|undefined>} 不可用时的替代路由
 */
export async function checkAuthCenterAccess(route, loadStatus) {
  if (!route.meta?.requiresAuthCenter) {
    return
  }
  let reason = 'unavailable'
  try {
    const response = await loadStatus()
    if (response.data?.enabled === true) {
      return
    }
    if (response.data?.enabled === false) {
      reason = 'disabled'
    }
  } catch {
    // 无法确认服务状态时停止进入表单，避免把网络故障误报为未启用。
  }
  return { path: '/auth-center/error', query: { reason }, replace: true }
}
