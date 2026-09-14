/**
 * 从地址片段读取认证交互的CSRF凭据。
 *
 * @param {string} hash 当前URL片段
 * @returns {string} CSRF凭据，缺失时返回空字符串
 */
export function readInteractionCsrf(hash) {
  if (typeof hash !== 'string') {
    return ''
  }
  return new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash).get('csrf') || ''
}

/**
 * 生成仅携带认证交互标识的页面地址。
 *
 * @param {string} path 认证页面路径
 * @param {string} interactionId 认证交互标识
 * @returns {string} 已编码交互标识的页面地址
 */
export function interactionRouteLocation(path, interactionId) {
  return `${path}?interaction=${encodeURIComponent(interactionId)}`
}

/**
 * 校验完成地址是否属于当前源和当前认证交互。
 *
 * @param {string} url 服务端返回的完成地址
 * @param {string} origin 当前页面源地址
 * @param {string} interactionId 当前认证交互标识
 * @returns {URL|null} 可信完成地址，校验失败时返回null
 */
export function trustedCompletionUrl(url, origin, interactionId) {
  if (typeof url !== 'string' || !url || typeof interactionId !== 'string' || !interactionId) {
    return null
  }
  let target
  try {
    target = new URL(url, origin)
  } catch {
    return null
  }
  const expectedPath = `/auth/interaction/${encodeURIComponent(interactionId)}/complete`
  return target.origin === origin && target.pathname === expectedPath ? target : null
}
