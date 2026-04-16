import config from "@/config";

const TRANSPORT_BASE_URL = config.baseUrl;
const EXCLUDED_URL_PATTERNS = [
  "/transport/crypto/frontend-config",
  "/transport/crypto/public-key",
  "/common/download",
  "/common/download/resource",
];
const TRANSPORT_FRONTEND_CONFIG_CACHE_KEY = "transportCryptoFrontendConfig";
const TRANSPORT_FRONTEND_CONFIG_URL = "/transport/crypto/frontend-config";
const TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS = 60;
const DEFAULT_TRANSPORT_ENVELOPE_VERSION = "1";
const DEFAULT_REQUEST_ENVELOPE_ALGORITHM = "RSA_OAEP_AES_256_GCM";
const DEFAULT_RESPONSE_ENVELOPE_ALGORITHM = "AES_256_GCM";
const DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH = 4096;

let cachedTransportPolicy = null;
let inflightTransportPolicyPromise = null;

/**
 * 获取当前 Unix 秒级时间戳。
 *
 * @returns {number} 当前时间戳
 */
function getNowTimestamp() {
  return Math.floor(Date.now() / 1000);
}

/**
 * 判断请求地址是否命中固定排除名单。
 *
 * @param {string} url 请求地址
 * @returns {boolean} 是否命中排除规则
 */
function matchExcludedUrl(url = "") {
  return EXCLUDED_URL_PATTERNS.some((pattern) => url.includes(pattern));
}

/**
 * 判断请求路径是否命中路径前缀列表。
 *
 * @param {string} path 待匹配路径
 * @param {string[]} pathPatterns 路径前缀集合
 * @returns {boolean} 是否匹配成功
 */
function matchPathPrefix(path = "", pathPatterns = []) {
  return pathPatterns.some(
    (pattern) => path === pattern || path.startsWith(`${pattern}/`),
  );
}

/**
 * 从绝对地址中提取 pathname，或直接返回相对地址的路径部分。
 *
 * @param {string} url 请求地址
 * @returns {string} 标准化后的路径
 */
function parseAbsoluteUrlPath(url = "") {
  const normalizedUrl = String(url || "");
  if (!normalizedUrl) {
    return "/";
  }
  if (
    !normalizedUrl.startsWith("http://") &&
    !normalizedUrl.startsWith("https://")
  ) {
    return normalizedUrl.split("?")[0] || "/";
  }
  const pathMatch = normalizedUrl.match(/^https?:\/\/[^/]+(\/[^?#]*)?/i);
  return pathMatch?.[1] || "/";
}

/**
 * 解析基础 API 地址对应的路径前缀。
 *
 * @param {string} baseUrl 基础 API 地址
 * @returns {string} 基础路径前缀
 */
function getBaseApiPath(baseUrl = TRANSPORT_BASE_URL) {
  if (!baseUrl) {
    return "";
  }
  const baseApiPath = parseAbsoluteUrlPath(baseUrl);
  return baseApiPath === "/" ? "" : baseApiPath;
}

/**
 * 计算后端用于 AAD 与策略匹配的标准请求路径。
 *
 * @param {string} url 请求地址
 * @param {string} baseUrl 基础 API 地址
 * @returns {string} 标准化请求路径
 */
function getRequestPath(url = "", baseUrl = TRANSPORT_BASE_URL) {
  const baseApiPath = getBaseApiPath(baseUrl);
  const pathname = parseAbsoluteUrlPath(url);
  if (baseApiPath && pathname.startsWith(baseApiPath)) {
    const normalizedPath = pathname.slice(baseApiPath.length);
    return normalizedPath || "/";
  }
  return pathname || "/";
}

/**
 * 标准化后端下发的路径列表配置。
 *
 * @param {Array} paths 原始路径集合
 * @returns {string[]} 标准化后的路径数组
 */
function normalizePaths(paths) {
  if (!Array.isArray(paths)) {
    return [];
  }
  return paths.map((path) => String(path || "").trim()).filter(Boolean);
}

/**
 * 从请求头对象中读取指定字段。
 *
 * @param {Object} headers 请求头对象
 * @param {string} name 请求头名称
 * @returns {*} 请求头值
 */
function getHeaderValue(headers, name) {
  if (!headers) {
    return undefined;
  }
  return headers[name] ?? headers[name.toLowerCase()] ?? headers[name.toUpperCase()];
}

/**
 * 将后端配置响应转换为前端统一使用的策略对象。
 *
 * @param {Object} payload 后端返回的配置数据
 * @returns {Object} 标准化后的传输加密策略
 */
function normalizeTransportPolicy(payload) {
  return {
    transportCryptoEnabled: Boolean(payload?.transportCryptoEnabled),
    transportCryptoMode: String(payload?.transportCryptoMode || "off"),
    transportCryptoActive: Boolean(payload?.transportCryptoActive),
    envelopeVersion: String(
      payload?.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    ),
    publicKeyUrl: String(payload?.publicKeyUrl || "/transport/crypto/public-key"),
    requestEnvelopeAlgorithm: String(
      payload?.requestEnvelopeAlgorithm || DEFAULT_REQUEST_ENVELOPE_ALGORITHM,
    ),
    responseEnvelopeAlgorithm: String(
      payload?.responseEnvelopeAlgorithm || DEFAULT_RESPONSE_ENVELOPE_ALGORITHM,
    ),
    enabledPaths: normalizePaths(payload?.enabledPaths),
    requiredPaths: normalizePaths(payload?.requiredPaths),
    excludePaths: normalizePaths(payload?.excludePaths),
    maxEncryptedGetUrlLength: Number(
      payload?.maxEncryptedGetUrlLength || DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH,
    ),
    configExpireAt: Number(payload?.configExpireAt || 0),
    retryAt: Number(payload?.retryAt || payload?.configExpireAt || 0),
  };
}

/**
 * 构建不可用场景下的本地兜底策略。
 *
 * @returns {Object} 明文回退策略
 */
function buildFallbackTransportPolicy() {
  const nowTimestamp = getNowTimestamp();
  return {
    transportCryptoEnabled: false,
    transportCryptoMode: "off",
    transportCryptoActive: false,
    envelopeVersion: DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    publicKeyUrl: "/transport/crypto/public-key",
    requestEnvelopeAlgorithm: DEFAULT_REQUEST_ENVELOPE_ALGORITHM,
    responseEnvelopeAlgorithm: DEFAULT_RESPONSE_ENVELOPE_ALGORITHM,
    enabledPaths: [],
    requiredPaths: [],
    excludePaths: [...EXCLUDED_URL_PATTERNS],
    maxEncryptedGetUrlLength: DEFAULT_TRANSPORT_MAX_GET_URL_LENGTH,
    configExpireAt:
      nowTimestamp + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS,
    retryAt: nowTimestamp + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS,
  };
}

/**
 * 基于旧策略生成短期可重试的缓存策略。
 *
 * @param {Object} policy 旧的策略对象
 * @returns {Object} 可重试策略
 */
function buildRetryableTransportPolicy(policy) {
  const normalizedPolicy = normalizeTransportPolicy(policy);
  return {
    ...normalizedPolicy,
    retryAt: getNowTimestamp() + TRANSPORT_FRONTEND_CONFIG_FALLBACK_TTL_SECONDS,
  };
}

/**
 * 判断当前策略是否仍在可用期内。
 *
 * @param {Object} policy 待校验策略
 * @returns {boolean} 是否可继续使用
 */
function isUsableTransportPolicy(policy) {
  if (!policy || !policy.publicKeyUrl || !policy.retryAt) {
    return false;
  }
  return policy.retryAt > getNowTimestamp();
}

/**
 * 从本地缓存加载最近一次持久化的策略。
 *
 * @returns {Object|null} 缓存策略
 */
function loadPersistedTransportPolicy() {
  const persistedTransportPolicy = uni.getStorageSync(
    TRANSPORT_FRONTEND_CONFIG_CACHE_KEY,
  );
  if (!persistedTransportPolicy) {
    return null;
  }
  return normalizeTransportPolicy(persistedTransportPolicy);
}

/**
 * 请求后端传输加密前端配置。
 * 这里直接使用原始 uni.request，避免策略初始化阶段反向依赖统一 request
 * 包装器，导致“是否加密尚未判定时又要先走加密请求”的循环依赖。
 *
 * @returns {Promise<Object>} Uni 请求响应结果
 */
function requestFrontendConfig() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${TRANSPORT_BASE_URL}${TRANSPORT_FRONTEND_CONFIG_URL}`,
      method: "GET",
      timeout: 10000,
      success: resolve,
      fail: reject,
    });
  });
}

/**
 * 获取请求加密使用的标准路径。
 *
 * @param {string} url 请求地址
 * @param {string} baseUrl 基础 API 地址
 * @returns {string} 标准请求路径
 */
export function getTransportRequestPath(
  url = "",
  baseUrl = TRANSPORT_BASE_URL,
) {
  return getRequestPath(url, baseUrl);
}

/**
 * 获取当前生效的传输加密策略。
 *
 * @returns {Object} 当前策略对象
 */
export function getTransportCryptoPolicy() {
  return cachedTransportPolicy || buildFallbackTransportPolicy();
}

/**
 * 清空当前策略缓存与持久化数据。
 *
 * @returns {void}
 */
export function invalidateTransportCryptoPolicy() {
  cachedTransportPolicy = null;
  inflightTransportPolicyPromise = null;
  uni.removeStorageSync(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY);
}

/**
 * 确保本地已加载一份可用的传输加密策略。
 *
 * @param {boolean} forceRefresh 是否强制从后端刷新
 * @returns {Promise<Object>} 当前可用策略
 */
export async function ensureTransportCryptoPolicyLoaded(forceRefresh = false) {
  if (!forceRefresh && !cachedTransportPolicy) {
    const persistedTransportPolicy = loadPersistedTransportPolicy();
    if (isUsableTransportPolicy(persistedTransportPolicy)) {
      cachedTransportPolicy = persistedTransportPolicy;
    }
  }

  if (!forceRefresh && isUsableTransportPolicy(cachedTransportPolicy)) {
    return cachedTransportPolicy;
  }

  if (inflightTransportPolicyPromise) {
    return inflightTransportPolicyPromise;
  }

  inflightTransportPolicyPromise = requestFrontendConfig()
    .then((response) => {
      const payload = normalizeTransportPolicy(response?.data?.data || {});
      cachedTransportPolicy = payload;
      uni.setStorageSync(TRANSPORT_FRONTEND_CONFIG_CACHE_KEY, payload);
      inflightTransportPolicyPromise = null;
      return cachedTransportPolicy;
    })
    .catch((error) => {
      const staleTransportPolicy =
        cachedTransportPolicy || loadPersistedTransportPolicy();
      inflightTransportPolicyPromise = null;
      cachedTransportPolicy = staleTransportPolicy
        ? buildRetryableTransportPolicy(staleTransportPolicy)
        : buildFallbackTransportPolicy();
      uni.setStorageSync(
        TRANSPORT_FRONTEND_CONFIG_CACHE_KEY,
        cachedTransportPolicy,
      );
      if (staleTransportPolicy) {
        console.warn(
          "加载传输加密前端配置失败，当前继续沿用最近一次后端策略",
          error,
        );
      } else {
        console.warn("加载传输加密前端配置失败，当前回退为明文请求策略", error);
      }
      return cachedTransportPolicy;
    });

  return inflightTransportPolicyPromise;
}

/**
 * 判断当前请求是否需要执行请求体加密。
 *
 * @param {Object} requestConfig 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否启用请求加密
 */
export function shouldEncryptRequest(
  requestConfig,
  transportPolicy = getTransportCryptoPolicy(),
) {
  if (!transportPolicy.transportCryptoActive) {
    return false;
  }
  const requestPath = getRequestPath(
    requestConfig.url,
    requestConfig.baseUrl || TRANSPORT_BASE_URL,
  );
  if (matchPathPrefix(requestPath, transportPolicy.excludePaths || [])) {
    return false;
  }
  if (
    (transportPolicy.enabledPaths || []).length &&
    !matchPathPrefix(requestPath, transportPolicy.enabledPaths || [])
  ) {
    return false;
  }
  if ((requestConfig.headers || {}).encrypt === false) {
    return false;
  }
  if (matchExcludedUrl(requestConfig.url)) {
    return false;
  }
  const contentType =
    getHeaderValue(requestConfig.header, "Content-Type") ||
    getHeaderValue(requestConfig.headers, "Content-Type") ||
    "";
  if (String(contentType).includes("multipart/form-data")) {
    return false;
  }
  return true;
}

/**
 * 判断当前响应是否需要执行自动解密。
 *
 * @param {Object} requestConfig 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否启用响应解密
 */
export function shouldEncryptResponse(
  requestConfig,
  transportPolicy = getTransportCryptoPolicy(),
) {
  const requestPath = getRequestPath(
    requestConfig.url,
    requestConfig.baseUrl || TRANSPORT_BASE_URL,
  );
  if (matchPathPrefix(requestPath, transportPolicy.excludePaths || [])) {
    return false;
  }
  if (
    (transportPolicy.enabledPaths || []).length &&
    !matchPathPrefix(requestPath, transportPolicy.enabledPaths || [])
  ) {
    return false;
  }
  if ((requestConfig.headers || {}).encryptResponse === false) {
    return false;
  }
  if (matchExcludedUrl(requestConfig.url)) {
    return false;
  }
  if (requestConfig.__transportCryptoEnabledForRequest === true) {
    return true;
  }
  if (requestConfig.__transportCryptoEnabledForRequest === false) {
    return false;
  }
  return transportPolicy.transportCryptoActive;
}

/**
 * 判断查询参数是否需要封装为加密信封。
 *
 * @param {Object} requestConfig 请求配置
 * @param {Object} transportPolicy 传输加密策略
 * @returns {boolean} 是否启用查询参数加密
 */
export function shouldEncryptQuery(
  requestConfig,
  transportPolicy = getTransportCryptoPolicy(),
) {
  if ((requestConfig.headers || {}).encryptQuery === false) {
    return false;
  }
  return shouldEncryptRequest(requestConfig, transportPolicy);
}
