import axios from 'axios'

import {
  ensureTransportCryptoPolicyLoaded,
  getTransportCryptoPolicy,
  shouldEncryptQuery,
  shouldEncryptRequest,
  shouldEncryptResponse
} from '@/utils/transportCryptoPolicy'
import cache from '@/plugins/cache'

const TRANSPORT_BASE_URL = import.meta.env.VITE_APP_BASE_API
const TRANSPORT_ENABLE_HEADER = 'X-Transport-Encrypt'
const TRANSPORT_KEY_ID_HEADER = 'X-Key-Id'
const ENCRYPTED_RESPONSE_HEADER = 'x-body-encrypted'
const DEFAULT_TRANSPORT_ENVELOPE_VERSION = '1'

const transportClient = axios.create({
  baseURL: TRANSPORT_BASE_URL,
  timeout: 10000
})

let cachedKeyMeta = null
let inflightKeyMetaPromise = null
const KEY_REFRESH_BUFFER_MIN_SECONDS = 30
const KEY_REFRESH_BUFFER_MAX_SECONDS = 300
const TRANSPORT_KEY_META_CACHE_KEY = 'transportCryptoKeyMeta'
const TRANSPORT_RETRYABLE_ERROR_MESSAGES = new Set(['Decryption failed', '密钥版本不存在'])

/**
 * 获取当前浏览器的 Web Crypto 实例。
 *
 * @returns {Crypto} 浏览器加密能力对象
 */
function getBrowserCrypto() {
  const browserCrypto = globalThis.crypto
  if (!browserCrypto?.subtle) {
    throw new Error('当前浏览器不支持 Web Crypto API')
  }
  return browserCrypto
}

/**
 * 从请求头对象中读取指定字段。
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
 * 为请求头对象设置指定字段。
 *
 * @param {Object|Headers} headers 请求头对象
 * @param {string} name 请求头名称
 * @param {*} value 请求头值
 * @returns {void}
 */
function setHeaderValue(headers, name, value) {
  if (!headers) {
    return
  }
  if (typeof headers.set === 'function') {
    headers.set(name, value)
    return
  }
  headers[name] = value
}

/**
 * 将字节数组编码为 Base64URL 文本。
 *
 * @param {Uint8Array} bytes 待编码字节数组
 * @returns {string} Base64URL 文本
 */
function toBase64Url(bytes) {
  let binary = ''
  bytes.forEach(byte => {
    binary += String.fromCharCode(byte)
  })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

/**
 * 将 Base64URL 文本还原为字节数组。
 *
 * @param {string} text Base64URL 文本
 * @returns {Uint8Array} 解码后的字节数组
 */
function fromBase64Url(text) {
  const normalizedText = text.replace(/-/g, '+').replace(/_/g, '/')
  const paddingLength = (4 - (normalizedText.length % 4 || 4)) % 4
  const binary = atob(normalizedText + '='.repeat(paddingLength))
  return Uint8Array.from(binary, char => char.charCodeAt(0))
}

/**
 * 将 PEM 公钥转换为 Web Crypto 可导入的 ArrayBuffer。
 *
 * @param {string} pem PEM 格式公钥
 * @returns {ArrayBuffer} DER 二进制内容
 */
function pemToArrayBuffer(pem) {
  const normalizedPem = pem.replace(/-----BEGIN PUBLIC KEY-----/g, '').replace(/-----END PUBLIC KEY-----/g, '').replace(/\s+/g, '')
  const binary = atob(normalizedPem)
  return Uint8Array.from(binary, char => char.charCodeAt(0)).buffer
}

/**
 * 对查询参数信封进行 JSON 编码后再转为 Base64URL。
 *
 * @param {Object} envelope 查询参数信封
 * @returns {string} 编码后的查询字符串片段
 */
function encodeQueryEnvelope(envelope) {
  const jsonText = JSON.stringify(envelope)
  return toBase64Url(new TextEncoder().encode(jsonText))
}

/**
 * 计算加密查询参数最终生成的 URL 长度。
 *
 * @param {string} url 请求地址
 * @param {Object} params 查询参数
 * @returns {number} URL 长度
 */
function buildQueryUrlLength(url = '', params = {}) {
  const queryText = new URLSearchParams(params).toString()
  if (!queryText) {
    return String(url || '').length
  }
  const normalizedUrl = String(url || '')
  const separator = normalizedUrl.includes('?') ? '&' : '?'
  return `${normalizedUrl}${separator}${queryText}`.length
}

/**
 * 获取基础 API 地址对应的路径前缀。
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
 * 计算参与 AAD 校验的标准请求路径。
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
 * 构建请求方向的 AAD 元数据。
 *
 * @param {Object} config Axios 请求配置
 * @returns {Object} 请求 AAD
 */
function buildRequestAad(config) {
  return {
    method: (config.method || 'get').toUpperCase(),
    path: getRequestPath(config.url)
  }
}

/**
 * 构建响应方向的 AAD 元数据。
 *
 * @param {Object} config Axios 请求配置
 * @returns {Object} 响应 AAD
 */
function buildResponseAad(config) {
  return {
    method: (config?.method || 'get').toUpperCase(),
    path: getRequestPath(config?.url),
    direction: 'response'
  }
}

/**
 * 将空值载荷规范化为可序列化对象。
 *
 * @param {*} payload 原始载荷
 * @returns {*} 规范化后的载荷
 */
function normalizePlainPayload(payload) {
  if (payload === undefined || payload === null) {
    return {}
  }
  return payload
}

/**
 * 将请求载荷序列化为 JSON 文本。
 *
 * @param {*} payload 原始载荷
 * @returns {string} JSON 文本
 */
function stringifyPayload(payload) {
  const normalizedPayload = normalizePlainPayload(payload)
  return JSON.stringify(normalizedPayload)
}

/**
 * 克隆请求配置中的可变字段，避免重试时互相污染。
 *
 * @param {*} value 待克隆值
 * @returns {*} 克隆结果
 */
function cloneRequestValue(value) {
  if (value === undefined || value === null) {
    return value
  }
  if (typeof globalThis.structuredClone === 'function') {
    return globalThis.structuredClone(value)
  }
  if (typeof value === 'object') {
    return JSON.parse(JSON.stringify(value))
  }
  return value
}

/**
 * 将信封字段转换为适合表单提交的字符串。
 *
 * @param {*} value 字段值
 * @returns {string} 序列化文本
 */
function stringifyEnvelopeField(value) {
  if (value && typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

/**
 * 将加密信封编码为表单字符串。
 *
 * @param {Object} envelope 信封对象
 * @returns {string} 表单编码文本
 */
function encodeFormEnvelope(envelope) {
  const formData = new URLSearchParams()
  Object.entries(envelope).forEach(([key, value]) => {
    formData.set(key, stringifyEnvelopeField(value))
  })
  return formData.toString()
}

/**
 * 将输入解析为 JSON 对象并校验结构。
 *
 * @param {*} payload 原始数据
 * @param {string} errorMessage 校验失败提示
 * @returns {Object} 解析后的对象
 */
function parseJsonObject(payload, errorMessage) {
  const parsedPayload = typeof payload === 'string' ? JSON.parse(payload) : payload
  if (!parsedPayload || typeof parsedPayload !== 'object' || Array.isArray(parsedPayload)) {
    throw new Error(errorMessage)
  }
  return parsedPayload
}

/**
 * 校验公钥接口响应壳是否有效。
 *
 * @param {Object} responsePayload 公钥接口原始响应
 * @returns {void}
 */
function validateTransportPublicKeyResponse(responsePayload) {
  if (responsePayload?.code !== 200 || !responsePayload?.data || typeof responsePayload.data !== 'object') {
    throw new Error(responsePayload?.msg || '获取传输层公钥失败')
  }
}

/**
 * 校验公钥业务载荷是否满足当前协议要求。
 *
 * @param {Object} payload 公钥业务载荷
 * @param {Object} transportPolicy 当前传输策略
 * @returns {void}
 */
function validateTransportPublicKeyPayload(payload, transportPolicy) {
  if (!payload?.publicKey || !payload?.kid) {
    throw new Error('获取传输层公钥失败')
  }
  if (String(payload.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION) !== transportPolicy.envelopeVersion) {
    throw new Error('传输层公钥协议版本不受支持')
  }
  if (payload.alg !== transportPolicy.requestEnvelopeAlgorithm) {
    throw new Error('传输层公钥算法不受支持')
  }
}

/**
 * 校验响应信封与当前请求上下文是否一致。
 *
 * @param {Object} envelope 响应信封
 * @param {Object} response Axios 响应对象
 * @param {Object} transportContext 请求加密上下文
 * @param {Object} transportPolicy 当前传输策略
 * @returns {void}
 */
function validateResponseEnvelope(envelope, response, transportContext, transportPolicy) {
  const expectedAad = buildResponseAad(response.config)
  const responseKid = getHeaderValue(response.headers, TRANSPORT_KEY_ID_HEADER)
  const aad = envelope.aad

  if (String(envelope.v || '') !== transportPolicy.envelopeVersion) {
    throw new Error('传输层响应协议版本不受支持')
  }
  if (String(envelope.alg || '') !== transportPolicy.responseEnvelopeAlgorithm) {
    throw new Error('传输层响应算法不受支持')
  }
  if (String(envelope.kid || '') !== String(transportContext.kid)) {
    throw new Error('传输层响应密钥版本不匹配')
  }
  if (responseKid && String(envelope.kid) !== String(responseKid)) {
    throw new Error('传输层响应头与响应体密钥版本不一致')
  }
  if (!aad || typeof aad !== 'object' || Array.isArray(aad)) {
    throw new Error('传输层响应AAD不合法')
  }
  if (String(aad.method || '').toUpperCase() !== expectedAad.method || String(aad.path || '') !== expectedAad.path) {
    throw new Error('传输层响应的method/path与当前请求不匹配')
  }
  if (String(aad.direction || '') !== expectedAad.direction) {
    throw new Error('传输层响应方向标识不合法')
  }
}

/**
 * 记录原始请求快照，供密钥刷新重试时恢复。
 *
 * @param {Object} config Axios 请求配置
 * @returns {void}
 */
function rememberOriginalRequestSnapshot(config) {
  if (config.__transportOriginalSnapshot) {
    return
  }
  config.__transportOriginalSnapshot = {
    url: config.url,
    params: cloneRequestValue(config.params),
    data: cloneRequestValue(config.data),
    contentType: getHeaderValue(config.headers, 'Content-Type')
  }
}

/**
 * 获取当前 Unix 秒级时间戳。
 *
 * @returns {number} 当前时间戳
 */
function getNowTimestamp() {
  return Math.floor(Date.now() / 1000)
}

/**
 * 根据公钥有效期计算本地提前刷新时间。
 *
 * @param {number} expireAt 公钥失效时间
 * @param {number} fetchedAt 公钥获取时间
 * @returns {number} 建议刷新时间
 */
function buildKeyRefreshAt(expireAt, fetchedAt = getNowTimestamp()) {
  const normalizedExpireAt = Number(expireAt || 0)
  const normalizedFetchedAt = Number(fetchedAt || 0)
  const ttlSeconds = Math.max(normalizedExpireAt - normalizedFetchedAt, 0)
  if (!normalizedExpireAt || !ttlSeconds) {
    return 0
  }
  const refreshBufferSeconds = Math.min(
    KEY_REFRESH_BUFFER_MAX_SECONDS,
    Math.max(KEY_REFRESH_BUFFER_MIN_SECONDS, Math.floor(ttlSeconds * 0.1))
  )
  return Math.max(normalizedFetchedAt, normalizedExpireAt - refreshBufferSeconds)
}

/**
 * 判断缓存中的公钥元数据是否仍可使用。
 *
 * @param {Object} keyMeta 公钥元数据
 * @param {number} nowTimestamp 当前时间戳
 * @returns {boolean} 是否可继续使用
 */
function isUsableKeyMeta(keyMeta, nowTimestamp = getNowTimestamp()) {
  if (!keyMeta?.publicKeyPem || !keyMeta?.kid || !keyMeta?.expireAt) {
    return false
  }
  const refreshAt = Number(keyMeta.refreshAt || buildKeyRefreshAt(keyMeta.expireAt, keyMeta.fetchedAt || nowTimestamp))
  return refreshAt > nowTimestamp
}

/**
 * 获取当前可用的后端公钥与密钥元信息。
 *
 * @param {boolean} forceRefresh 是否强制刷新
 * @returns {Promise<Object>} 公钥元信息
 */
async function getTransportKeyMeta(forceRefresh = false) {
  const transportPolicy = await ensureTransportCryptoPolicyLoaded()
  const nowTimestamp = getNowTimestamp()
  if (!forceRefresh && !cachedKeyMeta) {
    const persistedKeyMeta = cache.session.getJSON(TRANSPORT_KEY_META_CACHE_KEY)
    if (isUsableKeyMeta(persistedKeyMeta, nowTimestamp)) {
      const browserCrypto = getBrowserCrypto()
      const cryptoKey = await browserCrypto.subtle.importKey(
        'spki',
        pemToArrayBuffer(persistedKeyMeta.publicKeyPem),
        { name: 'RSA-OAEP', hash: 'SHA-256' },
        false,
        ['encrypt']
      )
      cachedKeyMeta = {
        kid: persistedKeyMeta.kid,
        alg: persistedKeyMeta.alg,
        envelopeVersion: persistedKeyMeta.envelopeVersion || transportPolicy.envelopeVersion,
        publicKey: cryptoKey,
        publicKeyPem: persistedKeyMeta.publicKeyPem,
        expireAt: persistedKeyMeta.expireAt,
        fetchedAt: persistedKeyMeta.fetchedAt || nowTimestamp,
        refreshAt: persistedKeyMeta.refreshAt || buildKeyRefreshAt(persistedKeyMeta.expireAt, persistedKeyMeta.fetchedAt || nowTimestamp)
      }
    }
  }
  if (!forceRefresh && isUsableKeyMeta(cachedKeyMeta, nowTimestamp)) {
    return cachedKeyMeta
  }
  if (inflightKeyMetaPromise) {
    return inflightKeyMetaPromise
  }
  inflightKeyMetaPromise = transportClient.get(transportPolicy.publicKeyUrl || '/transport/crypto/public-key').then(async response => {
    const responsePayload = response.data || {}
    const payload = responsePayload.data || {}
    const fetchedAt = getNowTimestamp()
    validateTransportPublicKeyResponse(responsePayload)
    validateTransportPublicKeyPayload(payload, transportPolicy)
    const browserCrypto = getBrowserCrypto()
    const cryptoKey = await browserCrypto.subtle.importKey(
      'spki',
      pemToArrayBuffer(payload.publicKey),
      { name: 'RSA-OAEP', hash: 'SHA-256' },
      false,
      ['encrypt']
    )
    cachedKeyMeta = {
      kid: payload.kid,
      alg: payload.alg,
      envelopeVersion: String(payload.envelopeVersion || transportPolicy.envelopeVersion),
      publicKey: cryptoKey,
      publicKeyPem: payload.publicKey,
      expireAt: payload.expireAt,
      fetchedAt,
      refreshAt: buildKeyRefreshAt(payload.expireAt, fetchedAt)
    }
    cache.session.setJSON(TRANSPORT_KEY_META_CACHE_KEY, {
      kid: payload.kid,
      alg: payload.alg,
      envelopeVersion: String(payload.envelopeVersion || transportPolicy.envelopeVersion),
      publicKeyPem: payload.publicKey,
      expireAt: payload.expireAt,
      fetchedAt,
      refreshAt: buildKeyRefreshAt(payload.expireAt, fetchedAt)
    })
    inflightKeyMetaPromise = null
    return cachedKeyMeta
  }).catch(error => {
    inflightKeyMetaPromise = null
    throw error
  })
  return inflightKeyMetaPromise
}

/**
 * 为当前请求创建一次性的对称密钥上下文。
 *
 * @returns {Promise<Object>} 请求级传输上下文
 */
async function buildTransportContext() {
  const browserCrypto = getBrowserCrypto()
  const keyMeta = await getTransportKeyMeta()
  const aesKey = await browserCrypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt'])
  const rawAesKey = new Uint8Array(await browserCrypto.subtle.exportKey('raw', aesKey))
  const encryptedAesKey = new Uint8Array(
    await browserCrypto.subtle.encrypt({ name: 'RSA-OAEP' }, keyMeta.publicKey, rawAesKey)
  )
  return {
    kid: keyMeta.kid,
    alg: keyMeta.alg,
    envelopeVersion: keyMeta.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    aesKey,
    ek: toBase64Url(encryptedAesKey)
  }
}

/**
 * 使用 AES-GCM 对明文载荷执行信封加密。
 *
 * @param {Object} context 请求级传输上下文
 * @param {string} plainText 明文内容
 * @param {Object} aad AAD 元数据
 * @returns {Promise<Object>} 加密信封
 */
async function encryptPayloadText(context, plainText, aad) {
  const browserCrypto = getBrowserCrypto()
  const iv = browserCrypto.getRandomValues(new Uint8Array(12))
  const ciphertext = new Uint8Array(
    await browserCrypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(JSON.stringify(aad)) },
      context.aesKey,
      new TextEncoder().encode(plainText)
    )
  )
  return {
    v: context.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    kid: context.kid,
    alg: context.alg,
    ts: Math.floor(Date.now() / 1000),
    nonce: browserCrypto.randomUUID(),
    ek: context.ek,
    aad,
    iv: toBase64Url(iv),
    ct: toBase64Url(ciphertext)
  }
}

/**
 * 使用请求上下文中的 AES 密钥解密响应信封。
 *
 * @param {Object} envelope 响应信封
 * @param {Object} context 请求级传输上下文
 * @returns {Promise<string>} 解密后的明文
 */
async function decryptEnvelope(envelope, context) {
  const browserCrypto = getBrowserCrypto()
  const decryptedBytes = await browserCrypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: fromBase64Url(envelope.iv),
      additionalData: new TextEncoder().encode(JSON.stringify(envelope.aad || {}))
    },
    context.aesKey,
    fromBase64Url(envelope.ct)
  )
  return new TextDecoder().decode(decryptedBytes)
}

/**
 * 复用同一次请求内的传输上下文，避免重复生成密钥。
 *
 * @param {Object} config Axios 请求配置
 * @returns {Promise<Object>} 请求级传输上下文
 */
function getOrCreateTransportContext(config) {
  if (config.__transportCryptoContextPromise) {
    return config.__transportCryptoContextPromise
  }
  config.__transportCryptoContextPromise = buildTransportContext()
  return config.__transportCryptoContextPromise
}

/**
 * 对 Axios 请求配置执行传输层加密封装。
 *
 * @param {Object} config Axios 请求配置
 * @returns {Promise<Object>} 加密后的请求配置
 */
export async function encryptTransportRequest(config) {
  const transportPolicy = await ensureTransportCryptoPolicyLoaded()
  if (!shouldEncryptRequest(config, transportPolicy)) {
    config.__transportCryptoEnabledForRequest = false
    return config
  }

  rememberOriginalRequestSnapshot(config)
  const transportContext = await getOrCreateTransportContext(config)
  const contentType = (getHeaderValue(config.headers, 'Content-Type') || 'application/json').toLowerCase()
  const method = (config.method || 'get').toLowerCase()
  const requestAad = buildRequestAad(config)

  if (shouldEncryptQuery(config, transportPolicy) && (config.params || method === 'get' || method === 'delete')) {
    const queryEnvelope = await encryptPayloadText(
      transportContext,
      JSON.stringify(normalizePlainPayload(config.params)),
      requestAad
    )
    config.params = { __enc: encodeQueryEnvelope(queryEnvelope) }
    if (buildQueryUrlLength(config.url, config.params) > Number(transportPolicy.maxEncryptedGetUrlLength || 4096)) {
      throw new Error('当前GET/DELETE请求参数加密后长度超限，请改用POST请求或精简查询条件')
    }
  }

  if (method === 'post' || method === 'put' || method === 'patch' || method === 'delete') {
    const plainText = stringifyPayload(config.data)
    const bodyEnvelope = await encryptPayloadText(transportContext, plainText, requestAad)
    if (contentType.includes('application/x-www-form-urlencoded')) {
      config.data = encodeFormEnvelope(bodyEnvelope)
    } else {
      config.data = bodyEnvelope
      setHeaderValue(config.headers, 'Content-Type', 'application/json;charset=utf-8')
    }
  }

  setHeaderValue(config.headers, TRANSPORT_ENABLE_HEADER, '1')
  setHeaderValue(config.headers, TRANSPORT_KEY_ID_HEADER, transportContext.kid)
  config.__transportCryptoContext = transportContext
  config.__transportCryptoEnabledForRequest = true
  return config
}

/**
 * 清空当前缓存的公钥元数据。
 *
 * @returns {void}
 */
export function invalidateTransportKeyMeta() {
  cachedKeyMeta = null
  inflightKeyMetaPromise = null
  cache.session.remove(TRANSPORT_KEY_META_CACHE_KEY)
}

/**
 * 将被加密改写过的请求恢复为原始形态。
 *
 * @param {Object} config Axios 请求配置
 * @returns {Object} 恢复后的请求配置
 */
export function resetTransportRequestConfig(config) {
  const originalSnapshot = config?.__transportOriginalSnapshot
  if (!config || !originalSnapshot) {
    return config
  }

  config.url = originalSnapshot.url
  config.params = cloneRequestValue(originalSnapshot.params)
  config.data = cloneRequestValue(originalSnapshot.data)
  if (originalSnapshot.contentType) {
    setHeaderValue(config.headers, 'Content-Type', originalSnapshot.contentType)
  }
  delete config.__transportCryptoContext
  delete config.__transportCryptoContextPromise
  delete config.__transportCryptoEnabledForRequest
  return config
}

/**
 * 判断错误是否属于可通过刷新公钥重试的场景。
 *
 * @param {Object} error 错误对象
 * @returns {boolean} 是否可刷新密钥重试
 */
export function shouldRetryTransportWithFreshKey(error) {
  const responseMsg = error?.response?.data?.msg
  const errorMessage = error?.message
  return TRANSPORT_RETRYABLE_ERROR_MESSAGES.has(responseMsg) || TRANSPORT_RETRYABLE_ERROR_MESSAGES.has(errorMessage)
}

/**
 * 解密成功响应中的传输层信封。
 *
 * @param {Object} response Axios 响应对象
 * @returns {Promise<Object>} 解密后的响应对象
 */
export async function decryptTransportResponse(response) {
  if (getHeaderValue(response.headers, ENCRYPTED_RESPONSE_HEADER) !== '1') {
    return response
  }
  if (!shouldEncryptResponse(response.config, getTransportCryptoPolicy())) {
    return response
  }
  const transportPolicy = getTransportCryptoPolicy()
  const transportContext = response.config.__transportCryptoContext
  if (!transportContext) {
    throw new Error('缺少响应解密上下文')
  }

  const envelope = parseJsonObject(response.data, '传输层响应信封格式不合法')
  validateResponseEnvelope(envelope, response, transportContext, transportPolicy)
  const plaintext = await decryptEnvelope(envelope, transportContext)
  response.data = JSON.parse(plaintext)
  return response
}

/**
 * 尝试解密异常响应中的传输层信封。
 *
 * @param {Object} error Axios 错误对象
 * @returns {Promise<Object>} 原始或已解密的错误对象
 */
export async function decryptTransportErrorResponse(error) {
  const response = error?.response
  if (!response || getHeaderValue(response.headers, ENCRYPTED_RESPONSE_HEADER) !== '1') {
    return error
  }
  if (!shouldEncryptResponse(response.config || {}, getTransportCryptoPolicy())) {
    return error
  }
  const transportPolicy = getTransportCryptoPolicy()
  const transportContext = response.config?.__transportCryptoContext
  if (!transportContext) {
    return error
  }

  try {
    const envelope = parseJsonObject(response.data, '传输层响应信封格式不合法')
    validateResponseEnvelope(envelope, response, transportContext, transportPolicy)
    const plaintext = await decryptEnvelope(envelope, transportContext)
    response.data = JSON.parse(plaintext)
  } catch (decryptError) {
    console.error(decryptError)
  }
  return error
}
