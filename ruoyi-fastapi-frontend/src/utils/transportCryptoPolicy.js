import axios from 'axios'

import cache from '@/plugins/cache'

const TRANSPORT_BASE_URL = import.meta.env.VITE_APP_BASE_API
const EXCLUDED_URL_PATTERNS = [
  '/transport/crypto/frontend-config',
  '/transport/crypto/public-key',
  '/common/download',
  '/common/download/resource'
]
const TRANSPORT_FRONTEND_CONFIG_CACHE_KEY = 'transportCryptoFrontendConfig'
const TRANSPORT_FRONTEND_CONFIG_URL = '/transport/crypto/frontend-config'
const TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS = 60
const DEFAULT_TRANSPORT_ENVELOPE_VERSION = '1'
const DEFAULT_REQUEST_ENVELOPE_ALGORITHM = 'RSA_OAEP_AES_256_GCM'
const DEFAULT_RESPONSE_ENVELOPE_ALGORITHM = 'AES_256_GCM'
const DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH = 4096

const transportPolicyClient = axios.create({
  baseURL: TRANSPORT_BASE_URL,
  timeout: 10000
})

let cachedTransportPolicy = null
let inflightTransportPolicyPromise = null

/**
 * 获取当前 Unix 秒级时间戳。
 *
 * @returns {number} 当前时间戳
 */
function getNowTimestamp() {
  return Math.floor(Date.now() / 1000)
}

/**
 * 判断请求地址是否命中固定排除名单。
 *
 * @param {string} url 请求地址
 * @returns {boolean} 是否命中排除规则
 */
function matchExcludedUrl(url = '') {
  return EXCLUDED_URL_PATTERNS.some(pattern => url.includes(pattern))
}

/**
 * 判断路径是否匹配指定前缀集合。
 *
 * @param {string} path 待匹配路径
 * @param {string[]} pathPatterns 路径前缀集合
 * @returns {boolean} 是否匹配成功
 */
function matchPathPrefix(path = '', pathPatterns = []) {
  return pathPatterns.some(pattern => path === pattern || path.startsWith(`${pattern}/`))
}

/**
 * 读取请求头中的指定字段，兼容原生对象与 Headers 实例。
 *
 * @param {Object|Headers} headers 请求头对象
 * @param {string} name 请求头名称
 * @returns {*} 请求头值
 */
function getHeaderValue(headers, name) {
  if (!headers) {
    return undefined
  }
  if (typeof headers.get === 'function') {
    return headers.get(name)
  }
  return headers[name] ?? headers[name.toLowerCase()]
}

/**
 * 解析基础 API 地址对应的路径前缀。
 *
 * @returns {string} 基础路径前缀
 */
function getBaseApiPath() {
  if (!TRANSPORT_BASE_URL) {
    return ''
  }
  if (TRANSPORT_BASE_URL.startsWith('http://') || TRANSPORT_BASE_URL.startsWith('https://')) {
    const baseApiPath = new URL(TRANSPORT_BASE_URL).pathname
    return baseApiPath === '/' ? '' : baseApiPath
  }
  return TRANSPORT_BASE_URL
}

/**
 * 计算用于策略匹配的标准请求路径。
 *
 * @param {string} url 请求地址
 * @returns {string} 标准化请求路径
 */
function getRequestPath(url = '') {
  const baseApiPath = getBaseApiPath()
  const normalizedUrl = String(url || '')

  let pathname = normalizedUrl
  if (normalizedUrl.startsWith('http://') || normalizedUrl.startsWith('https://')) {
    pathname = new URL(normalizedUrl).pathname
  } else {
    pathname = normalizedUrl.split('?')[0] || '/'
  }

  if (baseApiPath && pathname.startsWith(baseApiPath)) {
    const normalizedPath = pathname.slice(baseApiPath.length)
    return normalizedPath || '/'
  }
  return pathname || '/'
}

/**
 * 标准化后端下发的路径数组。
 *
 * @param {Array} paths 原始路径集合
 * @returns {string[]} 标准化后的路径列表
 */
function normalizePaths(paths) {
  if (!Array.isArray(paths)) {
    return []
  }
  return paths.map(path => String(path || '').trim()).filter(Boolean)
}

/**
 * 将后端配置响应转换为前端统一的策略对象。
 *
 * @param {Object} payload 后端返回配置
 * @returns {Object} 标准化后的策略对象
 */
function normalizeTransportPolicy(payload) {
  return {
    transportCryptoEnabled: Boolean(payload?.transportCryptoEnabled),
    transportCryptoMode: String(payload?.transportCryptoMode || 'off'),
    transportCryptoActive: Boolean(payload?.transportCryptoActive),
    envelopeVersion: String(payload?.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION),
    publicKeyUrl: String(payload?.publicKeyUrl || '/transport/crypto/public-key'),
    requestEnvelopeAlgorithm: String(payload?.requestEnvelopeAlgorithm || DEFAULT_REQUEST_ENVELOPE_ALGORITHM),
    responseEnvelopeAlgorithm: String(payload?.responseEnvelopeAlgorithm || DEFAULT_RESPONSE_ENVELOPE_ALGORITHM),
    enabledPaths: normalizePaths(payload?.enabledPaths),
    requiredPaths: normalizePaths(payload?.requiredPaths),
    excludePaths: normalizePaths(payload?.excludePaths),
    maxEncryptedGetUrlLength: Number(payload?.maxEncryptedGetUrlLength || DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH),
    configExpireAt: Number(payload?.configExpireAt || 0),
    retryAt: Number(payload?.retryAt || payload?.configExpireAt || 0)
  }
}

/**
 * 构建无法获取后端配置时的本地兜底策略。
 *
 * @returns {Object} 明文回退策略
 */
function buildFallbackTransportPolicy() {
  const nowTimestamp = getNowTimestamp()
  return {
    transportCryptoEnabled: false,
    transportCryptoMode: 'off',
    transportCryptoActive: false,
    envelopeVersion: DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    publicKeyUrl: '/transport/crypto/public-key',
    requestEnvelopeAlgorithm: DEFAULT_REQUEST_ENVELOPE_ALGORITHM,
    responseEnvelopeAlgorithm: DEFAULT_RESPONSE_ENVELOPE_ALGORITHM,
    enabledPaths: [],
    requiredPaths: [],
    excludePaths: [...EXCLUDED_URL_PATTERNS],
    maxEncryptedGetUrlLength: DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH,
    configExpireAt: nowTimestamp + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS,
    retryAt: nowTimestamp + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS
  }
}

/**
 * 基于旧策略构建短期可重试策略。
 *
 * @param {Object} policy 旧的策略对象
 * @returns {Object} 可重试策略
 */
function buildRetryableTransportPolicy(policy) {
  const normalizedPolicy = normalizeTransportPolicy(policy)
  const retryAt = getNowTimestamp() + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS
  return {
    ...normalizedPolicy,
    retryAt
  }
}

/**
 * 判断策略是否仍处于可用期内。
 *
 * @param {Object} policy 待校验策略
 * @returns {boolean} 是否可用
 */
function isUsableTransportPolicy(policy) {
  if (!policy) {
    return false
  }
  if (!policy.publicKeyUrl) {
    return false
  }
  if (!policy.retryAt) {
    return false
  }
  return policy.retryAt > getNowTimestamp()
}

/**
 * 从会话缓存读取最近一次持久化策略。
 *
 * @returns {Object|null} 缓存策略
 */
function loadPersistedTransportPolicy() {
  const persistedTransportPolicy = cache.session.getJSON(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY)
  if (!persistedTransportPolicy) {
    return null
  }
  return normalizeTransportPolicy(persistedTransportPolicy)
}

/**
 * 获取当前生效的传输加密策略。
 *
 * @returns {Object} 当前策略对象
 */
export function getTransportCryptoPolicy() {
  return cachedTransportPolicy || buildFallbackTransportPolicy()
}

/**
 * 清空当前策略缓存与会话缓存。
 *
 * @returns {void}
 */
export function invalidateTransportCryptoPolicy() {
  cachedTransportPolicy = null
  inflightTransportPolicyPromise = null
  cache.session.remove(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY)
}

/**
 * 确保本地已加载一份可用的传输加密策略。
 *
 * @param {boolean} forceRefresh 是否强制刷新策略
 * @returns {Promise<Object>} 当前可用策略
 */
export async function ensureTransportCryptoPolicyLoaded(forceRefresh = false) {
  if (!forceRefresh && !cachedTransportPolicy) {
    const persistedTransportPolicy = loadPersistedTransportPolicy()
    if (isUsableTransportPolicy(persistedTransportPolicy)) {
      cachedTransportPolicy = persistedTransportPolicy
    }
  }

  if (!forceRefresh && isUsableTransportPolicy(cachedTransportPolicy)) {
    return cachedTransportPolicy
  }

  if (inflightTransportPolicyPromise) {
    return inflightTransportPolicyPromise
  }

  inflightTransportPolicyPromise = transportPolicyClient.get(TRANSPORT_FRONTEND_CONFIG_URL).then(response => {
    const payload = normalizeTransportPolicy(response?.data?.data || {})
    cachedTransportPolicy = payload
    cache.session.setJSON(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY, payload)
    inflightTransportPolicyPromise = null
    return cachedTransportPolicy
  }).catch(error => {
    const staleTransportPolicy = cachedTransportPolicy || loadPersistedTransportPolicy()
    inflightTransportPolicyPromise = null
    cachedTransportPolicy = staleTransportPolicy
      ? buildRetryableTransportPolicy(staleTransportPolicy)
      : buildFallbackTransportPolicy()
    cache.session.setJSON(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY, cachedTransportPolicy)
    if (staleTransportPolicy) {
      console.warn('加载传输加密前端配置失败，当前继续沿用最近一次后端策略', error)
    } else {
      console.warn('加载传输加密前端配置失败，当前回退为明文请求策略', error)
    }
    return cachedTransportPolicy
  })

  return inflightTransportPolicyPromise
}

/**
 * 判断当前请求是否需要执行请求加密。
 *
 * @param {Object} config 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否需要加密
 */
export function shouldEncryptRequest(config, transportPolicy = getTransportCryptoPolicy()) {
  if (!transportPolicy.transportCryptoActive) {
    return false
  }
  const requestPath = getRequestPath(config.url)
  if (matchPathPrefix(requestPath, transportPolicy.excludePaths || [])) {
    return false
  }
  if ((transportPolicy.enabledPaths || []).length && !matchPathPrefix(requestPath, transportPolicy.enabledPaths || [])) {
    return false
  }
  if ((config.headers || {}).encrypt === false) {
    return false
  }
  if (matchExcludedUrl(config.url)) {
    return false
  }
  if (config.responseType === 'blob' || config.responseType === 'arraybuffer') {
    return false
  }
  const contentType = getHeaderValue(config.headers, 'Content-Type') || ''
  if (contentType.includes('multipart/form-data')) {
    return false
  }
  return true
}

/**
 * 判断当前响应是否需要执行自动解密。
 *
 * @param {Object} config 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否需要解密
 */
export function shouldEncryptResponse(config, transportPolicy = getTransportCryptoPolicy()) {
  const requestPath = getRequestPath(config.url)
  if (matchPathPrefix(requestPath, transportPolicy.excludePaths || [])) {
    return false
  }
  if ((transportPolicy.enabledPaths || []).length && !matchPathPrefix(requestPath, transportPolicy.enabledPaths || [])) {
    return false
  }
  if ((config.headers || {}).encryptResponse === false) {
    return false
  }
  if (matchExcludedUrl(config.url)) {
    return false
  }
  if (config.responseType === 'blob' || config.responseType === 'arraybuffer') {
    return false
  }
  if (config.__transportCryptoEnabledForRequest === true) {
    return true
  }
  if (config.__transportCryptoEnabledForRequest === false) {
    return false
  }
  return transportPolicy.transportCryptoActive
}

/**
 * 判断查询参数是否需要走加密信封流程。
 *
 * @param {Object} config 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否启用查询参数加密
 */
export function shouldEncryptQuery(config, transportPolicy = getTransportCryptoPolicy()) {
  if ((config.headers || {}).encryptQuery === false) {
    return false
  }
  return shouldEncryptRequest(config, transportPolicy)
}
