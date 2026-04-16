import config from "@/config";
import forge, { primeForgeRandomBytes } from "@/utils/transportForge";
import {
  ensureTransportCryptoPolicyLoaded,
  getTransportCryptoPolicy,
  getTransportRequestPath,
  shouldEncryptQuery,
  shouldEncryptRequest,
  shouldEncryptResponse,
} from "@/utils/transportCryptoPolicy";

const TRANSPORT_BASE_URL = config.baseUrl;
const TRANSPORT_ENABLE_HEADER = "X-Transport-Encrypt";
const TRANSPORT_KEY_ID_HEADER = "X-Key-Id";
const ENCRYPTED_RESPONSE_HEADER = "x-body-encrypted";
const DEFAULT_TRANSPORT_ENVELOPE_VERSION = "1";
const KEY_REFRESH_BUFFER_MIN_SECONDS = 30;
const KEY_REFRESH_BUFFER_MAX_SECONDS = 300;
const TRANSPORT_KEY_META_CACHE_KEY = "transportCryptoKeyMeta";
const TRANSPORT_RETRYABLE_ERROR_MESSAGES = new Set([
  "Decryption failed",
  "密钥版本不存在",
]);
const AES_GCM_TAG_LENGTH_BYTES = 16;
const FORGE_RANDOM_POOL_BYTES = 4096;

let cachedKeyMeta = null;
let inflightKeyMetaPromise = null;

/**
 * 获取当前运行时的全局对象引用。
 *
 * @returns {Object|undefined} 全局对象
 */
function getRuntimeGlobal() {
  if (typeof globalThis !== "undefined") {
    return globalThis;
  }
  if (typeof self !== "undefined") {
    return self;
  }
  if (typeof window !== "undefined") {
    return window;
  }
  if (typeof global !== "undefined") {
    return global;
  }
  return undefined;
}

/**
 * 为 Forge 补齐运行时依赖的全局对象别名。
 *
 * @returns {void}
 */
function ensureForgeRuntimeGlobal() {
  const runtimeGlobal = getRuntimeGlobal();
  if (!runtimeGlobal) {
    return;
  }
  if (typeof runtimeGlobal.self === "undefined") {
    runtimeGlobal.self = runtimeGlobal;
  }
  if (typeof runtimeGlobal.window === "undefined") {
    runtimeGlobal.window = runtimeGlobal;
  }
  if (typeof runtimeGlobal.global === "undefined") {
    runtimeGlobal.global = runtimeGlobal;
  }
}

/**
 * 获取已完成运行时适配的 Forge 实例。
 *
 * @returns {Promise<Object>} Forge 实例
 */
async function getForge() {
  ensureForgeRuntimeGlobal();
  return forge;
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
 * 为请求头对象设置指定字段。
 *
 * @param {Object} headers 请求头对象
 * @param {string} name 请求头名称
 * @param {*} value 请求头值
 * @returns {void}
 */
function setHeaderValue(headers, name, value) {
  if (!headers) {
    return;
  }
  headers[name] = value;
}

/**
 * 获取 Uni 响应对象中的响应头映射，兼容 H5 与其它平台字段差异。
 *
 * @param {Object} response Uni 响应对象
 * @returns {Object|undefined} 响应头对象
 */
function getResponseHeaders(response) {
  return response?.header || response?.headers;
}

/**
 * 将文本编码为 UTF-8 二进制字符串。
 *
 * @param {string} text 原始文本
 * @returns {string} UTF-8 二进制字符串
 */
function encodeUtf8(text) {
  if (typeof TextEncoder !== "undefined") {
    return uint8ArrayToBytes(new TextEncoder().encode(String(text || "")));
  }
  return unescape(encodeURIComponent(String(text || "")));
}

/**
 * 将 UTF-8 二进制字符串解码为文本。
 *
 * @param {string} bytes UTF-8 二进制字符串
 * @returns {string} 解码后的文本
 */
function decodeUtf8(bytes) {
  if (typeof TextDecoder !== "undefined") {
    return new TextDecoder().decode(bytesToUint8Array(bytes));
  }
  return decodeURIComponent(escape(bytes));
}

/**
 * 将 Uint8Array 转为 Forge 兼容的二进制字符串。
 *
 * @param {Uint8Array} uint8Array 字节数组
 * @returns {string} 二进制字符串
 */
function uint8ArrayToBytes(uint8Array) {
  return Array.from(uint8Array, (item) => String.fromCharCode(item)).join("");
}

/**
 * 将二进制字符串还原为 Uint8Array。
 *
 * @param {string} bytes 二进制字符串
 * @returns {Uint8Array} 字节数组
 */
function bytesToUint8Array(bytes) {
  return Uint8Array.from(String(bytes || ""), (item) => item.charCodeAt(0));
}

/**
 * 获取对象的内部类型标签。
 *
 * @param {*} value 待检测值
 * @returns {string} 内部类型标签
 */
function getObjectTag(value) {
  return Object.prototype.toString.call(value);
}

/**
 * 判断对象是否为 ArrayBuffer 视图。
 *
 * @param {*} value 待检测值
 * @returns {boolean} 是否为视图对象
 */
function isArrayBufferView(value) {
  return typeof ArrayBuffer !== "undefined" && ArrayBuffer.isView(value);
}

/**
 * 判断对象是否表现为 ArrayBuffer。
 *
 * @param {*} value 待检测值
 * @returns {boolean} 是否可按 ArrayBuffer 处理
 */
function isArrayBufferLike(value) {
  return (
    value instanceof ArrayBuffer ||
    getObjectTag(value) === "[object ArrayBuffer]" ||
    (value &&
      typeof value === "object" &&
      typeof value.byteLength === "number" &&
      typeof value.slice === "function" &&
      !("length" in value))
  );
}

/**
 * 判断对象是否为数组风格的字节容器。
 *
 * @param {*} value 待检测值
 * @returns {boolean} 是否可按字节数组处理
 */
function isByteArrayLikeObject(value) {
  return (
    value &&
    typeof value === "object" &&
    typeof value.length === "number" &&
    value.length >= 0
  );
}

/**
 * 尝试通过平台 Base64 API 归一化原生 ArrayBuffer 对象。
 *
 * @param {*} randomValues 平台返回的随机数字节对象
 * @returns {string|null} 归一化后的字节串，失败时返回 null
 */
function tryNormalizeArrayBufferLikeResult(randomValues) {
  const arrayBufferToBase64Api =
    (typeof uni !== "undefined" && uni.arrayBufferToBase64) ||
    (typeof wx !== "undefined" && wx.arrayBufferToBase64);
  const base64ToArrayBufferApi =
    (typeof uni !== "undefined" && uni.base64ToArrayBuffer) ||
    (typeof wx !== "undefined" && wx.base64ToArrayBuffer);

  if (!arrayBufferToBase64Api || !base64ToArrayBufferApi) {
    return null;
  }

  try {
    const base64Text = arrayBufferToBase64Api(randomValues);
    const arrayBuffer = base64ToArrayBufferApi(base64Text);
    return uint8ArrayToBytes(new Uint8Array(arrayBuffer));
  } catch (error) {
    return null;
  }
}

/**
 * 将平台返回的随机数字节结果统一转换为二进制字符串。
 *
 * @param {*} randomValues 平台返回结果
 * @param {number} expectedLength 期望字节长度
 * @returns {string} 归一化后的二进制字符串
 */
function normalizeRandomBytesResult(randomValues, expectedLength) {
  if (randomValues instanceof Uint8Array) {
    return uint8ArrayToBytes(randomValues);
  }
  if (isArrayBufferView(randomValues)) {
    return uint8ArrayToBytes(
      new Uint8Array(
        randomValues.buffer,
        randomValues.byteOffset || 0,
        randomValues.byteLength,
      ),
    );
  }
  if (randomValues instanceof ArrayBuffer) {
    return uint8ArrayToBytes(new Uint8Array(randomValues));
  }
  if (Array.isArray(randomValues)) {
    return uint8ArrayToBytes(Uint8Array.from(randomValues));
  }
  if (randomValues && typeof randomValues === "object") {
    if (randomValues.randomValues) {
      return normalizeRandomBytesResult(
        randomValues.randomValues,
        expectedLength,
      );
    }
    if (randomValues.value) {
      return normalizeRandomBytesResult(randomValues.value, expectedLength);
    }
    if (randomValues.data) {
      return normalizeRandomBytesResult(randomValues.data, expectedLength);
    }
    if (randomValues.buffer instanceof ArrayBuffer) {
      return normalizeRandomBytesResult(
        new Uint8Array(
          randomValues.buffer,
          randomValues.byteOffset || 0,
          randomValues.byteLength || expectedLength,
        ),
        expectedLength,
      );
    }
    if (isArrayBufferLike(randomValues)) {
      const normalizedBytes = tryNormalizeArrayBufferLikeResult(randomValues);
      if (normalizedBytes !== null) {
        return normalizedBytes;
      }
    }
    if (isByteArrayLikeObject(randomValues)) {
      return uint8ArrayToBytes(Uint8Array.from(randomValues));
    }
  }
  if (typeof randomValues === "string" && randomValues.length === expectedLength) {
    return randomValues;
  }
  throw new Error(
    `平台随机数返回结果格式不受支持: tag=${getObjectTag(randomValues)}, keys=${Object.keys(
      randomValues || {},
    ).join(",")}`,
  );
}

/**
 * 请求平台随机数字节并统一为二进制字符串。
 *
 * @param {Function} api 平台随机数 API
 * @param {number} length 需要的字节长度
 * @returns {Promise<string>} 随机数字节串
 */
function requestPlatformRandomBytes(api, length) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const resolveOnce = (result) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(normalizeRandomBytesResult(result, length));
    };
    const rejectOnce = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(error);
    };

    try {
      const maybeResult = api({
        length,
        success: resolveOnce,
        fail: rejectOnce,
      });
      if (maybeResult && typeof maybeResult.then === "function") {
        maybeResult.then(resolveOnce).catch(rejectOnce);
        return;
      }
      if (
        maybeResult &&
        (maybeResult.randomValues || maybeResult.value || maybeResult.data)
      ) {
        resolveOnce(maybeResult);
      }
    } catch (error) {
      rejectOnce(error);
    }
  });
}

/**
 * 在 app-plus iOS 端通过原生 NSUUID 获取随机字节兜底。
 *
 * @param {number} length 需要的字节长度
 * @returns {string|null} 随机数字节串，当前平台不支持时返回 null
 */
function getAppPlusIosRandomBytes(length) {
  // #ifdef APP-PLUS
  if (typeof plus === "undefined") {
    return null;
  }
  const osName = String(plus.os?.name || "").toLowerCase();
  if (osName !== "ios" || typeof plus.ios?.importClass !== "function") {
    return null;
  }

  try {
    const uuidClass = plus.ios.importClass("NSUUID");
    let randomBytes = "";
    while (randomBytes.length < length) {
      const uuidObject = plus.ios.invoke(uuidClass, "UUID");
      const uuidText = String(plus.ios.invoke(uuidObject, "UUIDString") || "")
        .replace(/-/g, "")
        .toLowerCase();
      plus.ios.deleteObject(uuidObject);
      if (!uuidText) {
        return null;
      }
      for (let index = 0; index < uuidText.length && randomBytes.length < length; index += 2) {
        const byteValue = parseInt(uuidText.slice(index, index + 2), 16);
        if (isNaN(byteValue)) {
          return null;
        }
        randomBytes += String.fromCharCode(byteValue);
      }
    }
    return randomBytes;
  } catch (error) {
    console.warn("iOS NSUUID 初始化失败，继续尝试其它随机数能力", error);
  }
  // #endif
  return null;
}

/**
 * 在 app-plus Android 端通过原生 SecureRandom 获取随机字节。
 *
 * @param {number} length 需要的字节长度
 * @returns {string|null} 随机数字节串，当前平台不支持时返回 null
 */
function getAppPlusAndroidRandomBytes(length) {
  // #ifdef APP-PLUS
  if (typeof plus === "undefined") {
    return null;
  }
  const osName = String(plus.os?.name || "").toLowerCase();
  if (osName !== "android" || typeof plus.android?.importClass !== "function") {
    return null;
  }

  try {
    plus.android.importClass("java.security.SecureRandom");
    const secureRandom =
      typeof plus.android.newObject === "function"
        ? plus.android.newObject("java.security.SecureRandom")
        : null;
    if (!secureRandom) {
      return null;
    }
    plus.android.importClass(secureRandom);
    let randomBytes = "";
    for (let index = 0; index < length; index += 1) {
      randomBytes += String.fromCharCode(secureRandom.nextInt(256));
    }
    if (typeof plus.android.autoCollection === "function") {
      plus.android.autoCollection(secureRandom);
    }
    return randomBytes;
  } catch (error) {
    console.warn("Android SecureRandom 初始化失败，继续尝试其它随机数能力", error);
  }
  // #endif
  return null;
}

/**
 * 获取当前运行环境下的安全随机数字节。
 *
 * @param {number} length 需要的字节长度
 * @returns {Promise<string>} 随机数字节串
 */
async function getRandomBytes(length) {
  const runtimeGlobal = getRuntimeGlobal();
  const runtimeCrypto = runtimeGlobal?.crypto;
  if (runtimeCrypto?.getRandomValues) {
    const bytes = new Uint8Array(length);
    runtimeCrypto.getRandomValues(bytes);
    return uint8ArrayToBytes(bytes);
  }
  if (typeof uni !== "undefined" && typeof uni.getRandomValues === "function") {
    return requestPlatformRandomBytes(uni.getRandomValues, length);
  }
  if (typeof wx !== "undefined" && typeof wx.getRandomValues === "function") {
    return requestPlatformRandomBytes(wx.getRandomValues, length);
  }
  const appPlusRandomBytes =
    getAppPlusAndroidRandomBytes(length) || getAppPlusIosRandomBytes(length);
  if (appPlusRandomBytes !== null) {
    return appPlusRandomBytes;
  }
  throw new Error("当前运行环境缺少安全随机数能力");
}

/**
 * 预填充 Forge 需要的随机数字节池。
 *
 * @param {number} length 预填充长度
 * @returns {Promise<void>}
 */
async function primeForgeRandomPool(length = FORGE_RANDOM_POOL_BYTES) {
  primeForgeRandomBytes(await getRandomBytes(length));
}

/**
 * 将二进制字符串编码为 Base64URL 文本。
 *
 * @param {string} bytes 二进制字符串
 * @returns {string} Base64URL 文本
 */
function toBase64Url(bytes) {
  const base64Text = uni.arrayBufferToBase64(bytesToUint8Array(bytes).buffer);
  return base64Text.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/**
 * 将 Base64URL 文本还原为二进制字符串。
 *
 * @param {string} text Base64URL 文本
 * @returns {string} 二进制字符串
 */
function fromBase64Url(text) {
  const normalizedText = String(text || "").replace(/-/g, "+").replace(/_/g, "/");
  const paddingLength = (4 - (normalizedText.length % 4 || 4)) % 4;
  const arrayBuffer = uni.base64ToArrayBuffer(
    normalizedText + "=".repeat(paddingLength),
  );
  return uint8ArrayToBytes(new Uint8Array(arrayBuffer));
}

/**
 * 将查询信封编码为可放入 URL 的字符串。
 *
 * @param {Object} envelope 查询信封
 * @returns {string} 编码后的查询参数值
 */
function encodeQueryEnvelope(envelope) {
  return toBase64Url(encodeUtf8(JSON.stringify(envelope)));
}

/**
 * 计算加密查询参数最终生成的 URL 长度。
 *
 * @param {string} url 请求地址
 * @param {Object} params 查询参数
 * @returns {number} URL 长度
 */
function buildQueryUrlLength(url = "", params = {}) {
  const queryText = Object.keys(params)
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`)
    .join("&");
  if (!queryText) {
    return String(url || "").length;
  }
  const normalizedUrl = String(url || "");
  const separator = normalizedUrl.includes("?") ? "&" : "?";
  return `${normalizedUrl}${separator}${queryText}`.length;
}

/**
 * 构建请求方向的 AAD 元数据。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {Object} 请求 AAD
 */
function buildRequestAad(requestConfig) {
  return {
    method: (requestConfig.method || "get").toUpperCase(),
    path: getTransportRequestPath(
      requestConfig.url,
      requestConfig.baseUrl || TRANSPORT_BASE_URL,
    ),
  };
}

/**
 * 构建响应方向的 AAD 元数据。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {Object} 响应 AAD
 */
function buildResponseAad(requestConfig) {
  return {
    method: (requestConfig.method || "get").toUpperCase(),
    path: getTransportRequestPath(
      requestConfig.url,
      requestConfig.baseUrl || TRANSPORT_BASE_URL,
    ),
    direction: "response",
  };
}

/**
 * 将空值载荷规范化为可序列化对象。
 *
 * @param {*} payload 原始载荷
 * @returns {*} 规范化后的载荷
 */
function normalizePlainPayload(payload) {
  if (payload === undefined || payload === null) {
    return {};
  }
  return payload;
}

/**
 * 将请求载荷序列化为 JSON 文本。
 *
 * @param {*} payload 原始载荷
 * @returns {string} JSON 文本
 */
function stringifyPayload(payload) {
  return JSON.stringify(normalizePlainPayload(payload));
}

/**
 * 克隆请求配置中的可变字段，便于失败重试恢复。
 *
 * @param {*} value 待克隆值
 * @returns {*} 克隆结果
 */
function cloneRequestValue(value) {
  if (value === undefined || value === null) {
    return value;
  }
  const runtimeGlobal = getRuntimeGlobal();
  if (typeof runtimeGlobal?.structuredClone === "function") {
    return runtimeGlobal.structuredClone(value);
  }
  if (typeof value === "object") {
    return JSON.parse(JSON.stringify(value));
  }
  return value;
}

/**
 * 将信封字段转换为适合表单提交的字符串。
 *
 * @param {*} value 字段值
 * @returns {string} 序列化文本
 */
function stringifyEnvelopeField(value) {
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

/**
 * 将加密信封编码为 x-www-form-urlencoded 文本。
 *
 * @param {Object} envelope 信封对象
 * @returns {string} 表单编码文本
 */
function encodeFormEnvelope(envelope) {
  return Object.entries(envelope)
    .map(
      ([key, value]) =>
        `${encodeURIComponent(key)}=${encodeURIComponent(
          stringifyEnvelopeField(value),
        )}`,
    )
    .join("&");
}

/**
 * 将输入解析为 JSON 对象并校验结构。
 *
 * @param {*} payload 原始数据
 * @param {string} errorMessage 失败提示
 * @returns {Object} 解析后的对象
 */
function parseJsonObject(payload, errorMessage) {
  const parsedPayload = typeof payload === "string" ? JSON.parse(payload) : payload;
  if (!parsedPayload || typeof parsedPayload !== "object" || Array.isArray(parsedPayload)) {
    throw new Error(errorMessage);
  }
  return parsedPayload;
}

/**
 * 基于随机字节生成 UUID v4 字符串。
 *
 * @returns {Promise<string>} UUID 文本
 */
async function createUuid() {
  const bytes = (await getRandomBytes(16))
    .split("")
    .map((item) => item.charCodeAt(0));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hexText = bytes
    .map((item) => item.toString(16).padStart(2, "0"))
    .join("");
  return `${hexText.slice(0, 8)}-${hexText.slice(8, 12)}-${hexText.slice(
    12,
    16,
  )}-${hexText.slice(16, 20)}-${hexText.slice(20)}`;
}

/**
 * 校验公钥接口响应壳是否有效。
 *
 * @param {Object} responsePayload 公钥接口原始响应
 * @returns {void}
 */
function validateTransportPublicKeyResponse(responsePayload) {
  if (
    responsePayload?.code !== 200 ||
    !responsePayload?.data ||
    typeof responsePayload.data !== "object"
  ) {
    throw new Error(responsePayload?.msg || "获取传输层公钥失败");
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
    throw new Error("获取传输层公钥失败");
  }
  if (
    String(payload.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION) !==
    transportPolicy.envelopeVersion
  ) {
    throw new Error("传输层公钥协议版本不受支持");
  }
  if (payload.alg !== transportPolicy.requestEnvelopeAlgorithm) {
    throw new Error("传输层公钥算法不受支持");
  }
}

/**
 * 校验响应信封与当前请求上下文是否一致。
 *
 * @param {Object} envelope 响应信封
 * @param {Object} response 原始响应对象
 * @param {Object} requestConfig 请求配置
 * @param {Object} transportContext 请求加密上下文
 * @param {Object} transportPolicy 当前传输策略
 * @returns {void}
 */
function validateResponseEnvelope(
  envelope,
  response,
  requestConfig,
  transportContext,
  transportPolicy,
) {
  const expectedAad = buildResponseAad(requestConfig);
  const responseKid = getHeaderValue(
    getResponseHeaders(response),
    TRANSPORT_KEY_ID_HEADER,
  );
  const aad = envelope.aad;

  if (String(envelope.v || "") !== transportPolicy.envelopeVersion) {
    throw new Error("传输层响应协议版本不受支持");
  }
  if (String(envelope.alg || "") !== transportPolicy.responseEnvelopeAlgorithm) {
    throw new Error("传输层响应算法不受支持");
  }
  if (String(envelope.kid || "") !== String(transportContext.kid)) {
    throw new Error("传输层响应密钥版本不匹配");
  }
  if (responseKid && String(envelope.kid) !== String(responseKid)) {
    throw new Error("传输层响应头与响应体密钥版本不一致");
  }
  if (!aad || typeof aad !== "object" || Array.isArray(aad)) {
    throw new Error("传输层响应AAD不合法");
  }
  if (
    String(aad.method || "").toUpperCase() !== expectedAad.method ||
    String(aad.path || "") !== expectedAad.path
  ) {
    throw new Error("传输层响应的method/path与当前请求不匹配");
  }
  if (String(aad.direction || "") !== expectedAad.direction) {
    throw new Error("传输层响应方向标识不合法");
  }
}

/**
 * 记录原始请求快照，供密钥刷新后重试恢复。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {void}
 */
function rememberOriginalRequestSnapshot(requestConfig) {
  if (requestConfig.__transportOriginalSnapshot) {
    return;
  }
  requestConfig.__transportOriginalSnapshot = {
    url: requestConfig.url,
    params: cloneRequestValue(requestConfig.params),
    data: cloneRequestValue(requestConfig.data),
    contentType: getHeaderValue(requestConfig.header, "Content-Type"),
  };
}

/**
 * 获取当前 Unix 秒级时间戳。
 *
 * @returns {number} 当前时间戳
 */
function getNowTimestamp() {
  return Math.floor(Date.now() / 1000);
}

/**
 * 根据公钥有效期计算本地提前刷新时间。
 *
 * @param {number} expireAt 公钥过期时间
 * @param {number} fetchedAt 公钥获取时间
 * @returns {number} 建议刷新时间
 */
function buildKeyRefreshAt(expireAt, fetchedAt = getNowTimestamp()) {
  const normalizedExpireAt = Number(expireAt || 0);
  const normalizedFetchedAt = Number(fetchedAt || 0);
  const ttlSeconds = Math.max(normalizedExpireAt - normalizedFetchedAt, 0);
  if (!normalizedExpireAt || !ttlSeconds) {
    return 0;
  }
  const refreshBufferSeconds = Math.min(
    KEY_REFRESH_BUFFER_MAX_SECONDS,
    Math.max(KEY_REFRESH_BUFFER_MIN_SECONDS, Math.floor(ttlSeconds * 0.1)),
  );
  return Math.max(normalizedFetchedAt, normalizedExpireAt - refreshBufferSeconds);
}

/**
 * 判断当前缓存的公钥元数据是否仍可使用。
 *
 * @param {Object} keyMeta 公钥元数据
 * @param {number} nowTimestamp 当前时间戳
 * @returns {boolean} 是否仍可使用
 */
function isUsableKeyMeta(keyMeta, nowTimestamp = getNowTimestamp()) {
  if (!keyMeta?.publicKeyPem || !keyMeta?.kid || !keyMeta?.expireAt) {
    return false;
  }
  const refreshAt = Number(
    keyMeta.refreshAt ||
      buildKeyRefreshAt(keyMeta.expireAt, keyMeta.fetchedAt || nowTimestamp),
  );
  return refreshAt > nowTimestamp;
}

/**
 * 请求后端公钥接口。
 * 这里故意直接使用原始 uni.request，避免在获取公钥前再次进入统一 request
 * 包装器而形成“加密请求依赖公钥、公钥请求又依赖加密请求”的启动环路。
 *
 * @param {string} publicKeyUrl 公钥接口地址
 * @returns {Promise<Object>} Uni 请求响应
 */
function requestPublicKey(publicKeyUrl) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${TRANSPORT_BASE_URL}${publicKeyUrl}`,
      method: "GET",
      timeout: 10000,
      success: resolve,
      fail: reject,
    });
  });
}

/**
 * 获取当前可用的后端公钥元信息。
 *
 * @param {boolean} forceRefresh 是否强制刷新
 * @returns {Promise<Object>} 公钥元信息
 */
async function getTransportKeyMeta(forceRefresh = false) {
  const transportPolicy = await ensureTransportCryptoPolicyLoaded();
  const nowTimestamp = getNowTimestamp();
  if (!forceRefresh && !cachedKeyMeta) {
    const persistedKeyMeta = uni.getStorageSync(TRANSPORT_KEY_META_CACHE_KEY);
    if (isUsableKeyMeta(persistedKeyMeta, nowTimestamp)) {
      cachedKeyMeta = {
        kid: persistedKeyMeta.kid,
        alg: persistedKeyMeta.alg,
        envelopeVersion:
          persistedKeyMeta.envelopeVersion || transportPolicy.envelopeVersion,
        publicKeyPem: persistedKeyMeta.publicKeyPem,
        expireAt: persistedKeyMeta.expireAt,
        fetchedAt: persistedKeyMeta.fetchedAt || nowTimestamp,
        refreshAt:
          persistedKeyMeta.refreshAt ||
          buildKeyRefreshAt(
            persistedKeyMeta.expireAt,
            persistedKeyMeta.fetchedAt || nowTimestamp,
          ),
      };
    }
  }
  if (!forceRefresh && isUsableKeyMeta(cachedKeyMeta, nowTimestamp)) {
    return cachedKeyMeta;
  }
  if (inflightKeyMetaPromise) {
    return inflightKeyMetaPromise;
  }
  inflightKeyMetaPromise = requestPublicKey(
    transportPolicy.publicKeyUrl || "/transport/crypto/public-key",
  )
    .then((response) => {
      const responsePayload = response.data || {};
      const payload = responsePayload.data || {};
      const fetchedAt = getNowTimestamp();
      validateTransportPublicKeyResponse(responsePayload);
      validateTransportPublicKeyPayload(payload, transportPolicy);
      cachedKeyMeta = {
        kid: payload.kid,
        alg: payload.alg,
        envelopeVersion: String(
          payload.envelopeVersion || transportPolicy.envelopeVersion,
        ),
        publicKeyPem: payload.publicKey,
        expireAt: payload.expireAt,
        fetchedAt,
        refreshAt: buildKeyRefreshAt(payload.expireAt, fetchedAt),
      };
      uni.setStorageSync(TRANSPORT_KEY_META_CACHE_KEY, cachedKeyMeta);
      inflightKeyMetaPromise = null;
      return cachedKeyMeta;
    })
    .catch((error) => {
      inflightKeyMetaPromise = null;
      throw error;
    });
  return inflightKeyMetaPromise;
}

/**
 * 使用 RSA-OAEP 加密当前请求的 AES 会话密钥。
 *
 * @param {string} publicKeyPem PEM 格式公钥
 * @param {string} aesKeyBytes AES 会话密钥字节串
 * @returns {Promise<string>} 加密后的会话密钥
 */
async function rsaEncryptAesKey(publicKeyPem, aesKeyBytes) {
  const cryptoForge = await getForge();
  await primeForgeRandomPool();
  const publicKey = cryptoForge.pki.publicKeyFromPem(String(publicKeyPem || ""));
  return publicKey.encrypt(aesKeyBytes, "RSA-OAEP", {
    md: cryptoForge.md.sha256.create(),
    mgf1: {
      md: cryptoForge.md.sha256.create(),
    },
  });
}

/**
 * 为当前请求构建一次性的传输加密上下文。
 *
 * @returns {Promise<Object>} 请求级传输上下文
 */
async function buildTransportContext() {
  const keyMeta = await getTransportKeyMeta();
  const aesKey = await getRandomBytes(32);
  const encryptedAesKey = await rsaEncryptAesKey(keyMeta.publicKeyPem, aesKey);
  return {
    kid: keyMeta.kid,
    alg: keyMeta.alg,
    envelopeVersion: keyMeta.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    aesKey,
    ek: toBase64Url(encryptedAesKey),
  };
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
  const cryptoForge = await getForge();
  const iv = await getRandomBytes(12);
  const cipher = cryptoForge.cipher.createCipher("AES-GCM", context.aesKey);
  cipher.start({
    iv,
    additionalData: encodeUtf8(JSON.stringify(aad)),
    tagLength: AES_GCM_TAG_LENGTH_BYTES * 8,
  });
  cipher.update(cryptoForge.util.createBuffer(encodeUtf8(plainText)));
  if (!cipher.finish()) {
    throw new Error("Encryption failed");
  }
  const ciphertext = cipher.output.getBytes() + cipher.mode.tag.getBytes();
  return {
    v: context.envelopeVersion || DEFAULT_TRANSPORT_ENVELOPE_VERSION,
    kid: context.kid,
    alg: context.alg,
    ts: getNowTimestamp(),
    nonce: await createUuid(),
    ek: context.ek,
    aad,
    iv: toBase64Url(iv),
    ct: toBase64Url(ciphertext),
  };
}

/**
 * 使用请求上下文中的 AES 密钥解密响应信封。
 *
 * @param {Object} envelope 响应信封
 * @param {Object} context 请求级传输上下文
 * @returns {Promise<string>} 解密后的明文
 */
async function decryptEnvelope(envelope, context) {
  const cryptoForge = await getForge();
  const encryptedPayload = fromBase64Url(envelope.ct);
  if (encryptedPayload.length <= AES_GCM_TAG_LENGTH_BYTES) {
    throw new Error("Decryption failed");
  }
  const ciphertext = encryptedPayload.slice(0, -AES_GCM_TAG_LENGTH_BYTES);
  const tag = encryptedPayload.slice(-AES_GCM_TAG_LENGTH_BYTES);
  const decipher = cryptoForge.cipher.createDecipher("AES-GCM", context.aesKey);
  decipher.start({
    iv: fromBase64Url(envelope.iv),
    additionalData: encodeUtf8(JSON.stringify(envelope.aad || {})),
    tagLength: AES_GCM_TAG_LENGTH_BYTES * 8,
    tag,
  });
  decipher.update(cryptoForge.util.createBuffer(ciphertext));
  if (!decipher.finish()) {
    throw new Error("Decryption failed");
  }
  return decodeUtf8(decipher.output.getBytes());
}

/**
 * 复用同一次请求内的传输上下文，避免重复生成密钥。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {Promise<Object>} 请求级传输上下文
 */
function getOrCreateTransportContext(requestConfig) {
  if (requestConfig.__transportCryptoContextPromise) {
    return requestConfig.__transportCryptoContextPromise;
  }
  requestConfig.__transportCryptoContextPromise = buildTransportContext();
  return requestConfig.__transportCryptoContextPromise;
}

/**
 * 对 Uni 请求配置执行传输层加密封装。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {Promise<Object>} 加密后的请求配置
 */
export async function encryptTransportRequest(requestConfig) {
  const transportPolicy = await ensureTransportCryptoPolicyLoaded();
  if (!shouldEncryptRequest(requestConfig, transportPolicy)) {
    requestConfig.__transportCryptoEnabledForRequest = false;
    return requestConfig;
  }

  rememberOriginalRequestSnapshot(requestConfig);
  const transportContext = await getOrCreateTransportContext(requestConfig);
  const contentType = String(
    getHeaderValue(requestConfig.header, "Content-Type") || "application/json",
  ).toLowerCase();
  const method = (requestConfig.method || "get").toLowerCase();
  const requestAad = buildRequestAad(requestConfig);

  if (
    shouldEncryptQuery(requestConfig, transportPolicy) &&
    (requestConfig.params || method === "get" || method === "delete")
  ) {
    const queryEnvelope = await encryptPayloadText(
      transportContext,
      JSON.stringify(normalizePlainPayload(requestConfig.params)),
      requestAad,
    );
    requestConfig.params = { __enc: encodeQueryEnvelope(queryEnvelope) };
    if (
      buildQueryUrlLength(requestConfig.url, requestConfig.params) >
      Number(transportPolicy.maxEncryptedGetUrlLength || 4096)
    ) {
      throw new Error(
        "当前GET/DELETE请求参数加密后长度超限，请改用POST请求或精简查询条件",
      );
    }
  }

  if (["post", "put", "patch", "delete"].includes(method)) {
    const plainText = stringifyPayload(requestConfig.data);
    const bodyEnvelope = await encryptPayloadText(
      transportContext,
      plainText,
      requestAad,
    );
    if (contentType.includes("application/x-www-form-urlencoded")) {
      requestConfig.data = encodeFormEnvelope(bodyEnvelope);
    } else {
      requestConfig.data = bodyEnvelope;
      setHeaderValue(
        requestConfig.header,
        "Content-Type",
        "application/json;charset=utf-8",
      );
    }
  }

  setHeaderValue(requestConfig.header, TRANSPORT_ENABLE_HEADER, "1");
  setHeaderValue(requestConfig.header, TRANSPORT_KEY_ID_HEADER, transportContext.kid);
  requestConfig.__transportCryptoContext = transportContext;
  requestConfig.__transportCryptoEnabledForRequest = true;
  return requestConfig;
}

/**
 * 清空当前缓存的公钥元数据。
 *
 * @returns {void}
 */
export function invalidateTransportKeyMeta() {
  cachedKeyMeta = null;
  inflightKeyMetaPromise = null;
  uni.removeStorageSync(TRANSPORT_KEY_META_CACHE_KEY);
}

/**
 * 将被加密改写过的请求恢复为原始形态。
 *
 * @param {Object} requestConfig 请求配置
 * @returns {Object} 恢复后的请求配置
 */
export function resetTransportRequestConfig(requestConfig) {
  const originalSnapshot = requestConfig?.__transportOriginalSnapshot;
  if (!requestConfig || !originalSnapshot) {
    return requestConfig;
  }

  requestConfig.url = originalSnapshot.url;
  requestConfig.params = cloneRequestValue(originalSnapshot.params);
  requestConfig.data = cloneRequestValue(originalSnapshot.data);
  if (originalSnapshot.contentType) {
    setHeaderValue(requestConfig.header, "Content-Type", originalSnapshot.contentType);
  }
  delete requestConfig.__transportCryptoContext;
  delete requestConfig.__transportCryptoContextPromise;
  delete requestConfig.__transportCryptoEnabledForRequest;
  return requestConfig;
}

/**
 * 判断错误是否属于可通过刷新公钥进行重试的场景。
 *
 * @param {Object} responseOrError 响应对象或错误对象
 * @returns {boolean} 是否可刷新密钥重试
 */
export function shouldRetryTransportWithFreshKey(responseOrError) {
  const responseMsg = responseOrError?.data?.msg || responseOrError?.response?.data?.msg;
  const errorMessage = responseOrError?.message;
  return (
    TRANSPORT_RETRYABLE_ERROR_MESSAGES.has(responseMsg) ||
    TRANSPORT_RETRYABLE_ERROR_MESSAGES.has(errorMessage)
  );
}

/**
 * 解密成功响应中的传输层信封。
 *
 * @param {Object} response 原始响应对象
 * @param {Object} requestConfig 请求配置
 * @returns {Promise<Object>} 解密后的响应对象
 */
export async function decryptTransportResponse(response, requestConfig) {
  const encryptedResponseFlag = String(
    getHeaderValue(getResponseHeaders(response), ENCRYPTED_RESPONSE_HEADER) || "",
  );
  if (encryptedResponseFlag !== "1") {
    return response;
  }
  if (!shouldEncryptResponse(requestConfig, getTransportCryptoPolicy())) {
    return response;
  }
  const transportPolicy = getTransportCryptoPolicy();
  const transportContext = requestConfig.__transportCryptoContext;
  if (!transportContext) {
    throw new Error("缺少响应解密上下文");
  }

  const envelope = parseJsonObject(response.data, "传输层响应信封格式不合法");
  validateResponseEnvelope(
    envelope,
    response,
    requestConfig,
    transportContext,
    transportPolicy,
  );
  const plaintext = await decryptEnvelope(envelope, transportContext);
  response.data = JSON.parse(plaintext);
  return response;
}

/**
 * 尝试解密异常响应中的传输层信封。
 *
 * @param {Object} error 错误对象
 * @param {Object} requestConfig 原始请求配置
 * @returns {Promise<Object>} 原始或已解密的错误对象
 */
export async function decryptTransportErrorResponse(error, requestConfig) {
  const response =
    error?.response ||
    (error && (error.data !== undefined || error.header || error.headers || error.statusCode)
      ? error
      : null);
  const encryptedResponseFlag = String(
    getHeaderValue(getResponseHeaders(response), ENCRYPTED_RESPONSE_HEADER) || "",
  );
  if (!response || encryptedResponseFlag !== "1") {
    return error;
  }
  if (!shouldEncryptResponse(requestConfig || {}, getTransportCryptoPolicy())) {
    return error;
  }
  const transportPolicy = getTransportCryptoPolicy();
  const transportContext = requestConfig?.__transportCryptoContext;
  if (!transportContext) {
    return error;
  }

  try {
    const envelope = parseJsonObject(response.data, "传输层响应信封格式不合法");
    validateResponseEnvelope(
      envelope,
      response,
      requestConfig,
      transportContext,
      transportPolicy,
    );
    const plaintext = await decryptEnvelope(envelope, transportContext);
    response.data = JSON.parse(plaintext);
    if (!error.response) {
      error.response = response;
    }
  } catch (decryptError) {
    console.error(decryptError);
  }
  return error;
}
