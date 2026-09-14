const DEVELOPMENT_HTTP_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])
const URI_TYPES = new Set(['redirect', 'post_logout', 'backchannel_logout', 'cors_origin'])

/**
 * 拆分并清理注册地址列表。
 *
 * @param {string} value 逗号或换行分隔的注册地址
 * @returns {string[]} 非空注册地址列表
 */
export function splitRegisteredUris(value) {
  return String(value || '')
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

/**
 * 校验单个客户端注册地址。
 *
 * @param {string} value 完整注册地址
 * @param {string} uriType 注册地址类型
 * @returns {string} 校验通过的原始地址
 * @throws {Error} 地址不符合对应类型的注册规则
 */
export function validateRegisteredUri(value, uriType) {
  if (!URI_TYPES.has(uriType)) {
    throw new Error('URI 类型无效')
  }
  if (typeof value !== 'string' || !value || value.length > 1000) {
    throw new Error('URI 长度必须为 1 到 1000 个字符')
  }
  if (value.includes('*')) {
    throw new Error('URI 不允许使用通配符')
  }

  let target
  try {
    target = new URL(value)
  } catch {
    throw new Error('URI 必须是完整的 HTTP 或 HTTPS 地址')
  }
  if (!['http:', 'https:'].includes(target.protocol) || !target.hostname) {
    throw new Error('URI 必须是完整的 HTTP 或 HTTPS 地址')
  }
  if (target.username || target.password) {
    throw new Error('URI 不允许包含用户信息')
  }
  if (target.hash) {
    throw new Error('URI 不允许包含 Fragment')
  }
  if (target.protocol === 'http:' && !DEVELOPMENT_HTTP_HOSTS.has(target.hostname.toLowerCase())) {
    throw new Error('仅本地开发地址允许使用 HTTP')
  }
  if (uriType === 'backchannel_logout' && target.search) {
    throw new Error('Back-Channel URI 不允许包含查询参数')
  }
  if (
    uriType === 'cors_origin' &&
    (target.pathname !== '/' || target.search || value.endsWith('/'))
  ) {
    throw new Error('CORS Origin 只能包含协议、主机和端口')
  }
  return value
}

/**
 * 校验客户端注册地址列表。
 *
 * @param {string} value 逗号或换行分隔的注册地址
 * @param {string} uriType 注册地址类型
 * @param {boolean} required 是否至少需要一个地址
 * @returns {string[]} 校验通过的注册地址列表
 * @throws {Error} 地址为空或不符合注册规则
 */
export function validateRegisteredUriList(value, uriType, required = false) {
  const uris = splitRegisteredUris(value)
  if (required && uris.length === 0) {
    throw new Error('请至少填写一个 Redirect URI')
  }
  uris.forEach((uri) => validateRegisteredUri(uri, uriType))
  return uris
}
