/**
 * 标准化实际请求路径，供传输加密策略匹配和 AAD 校验共用。
 *
 * @param {string} url 请求地址
 * @param {string} baseApi 宿主 API 基础地址
 * @param {string} pluginBase 插件部署前缀
 * @returns {string} 标准化请求路径
 */
export function normalizeTransportPath(url = '', baseApi = '', pluginBase = '') {
  const raw = String(url || '')
  let pathname = /^https?:\/\//.test(raw) ? new URL(raw).pathname : raw.split('?')[0] || '/'
  // 挂载插件使用独立于 baseApi 的同源路径，先移除插件部署前缀。
  const prefix = pluginBase.replace(/\/$/, '')
  if (
    prefix &&
    (pathname.startsWith(`${prefix}/apps/`) || pathname.startsWith(`${prefix}/plugin/runtime/`))
  ) {
    return pathname.slice(prefix.length)
  }
  const basePath = /^https?:\/\//.test(baseApi) ? new URL(baseApi).pathname : baseApi
  const normalizedBase = basePath.replace(/\/$/, '')
  if (
    normalizedBase &&
    (pathname === normalizedBase || pathname.startsWith(`${normalizedBase}/`))
  ) {
    pathname = pathname.slice(normalizedBase.length)
  }
  return pathname || '/'
}
