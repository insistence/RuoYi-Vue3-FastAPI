import forge from "node-forge/lib/forge";
import "node-forge/lib/util";
import "node-forge/lib/asn1";
import "node-forge/lib/oids";
import "node-forge/lib/cipher";
import "node-forge/lib/cipherModes";
import "node-forge/lib/aes";
import "node-forge/lib/jsbn";
import "node-forge/lib/pkcs1";
import "node-forge/lib/prime";
import "node-forge/lib/random";
import "node-forge/lib/md";
import "node-forge/lib/sha256";
import "node-forge/lib/mgf1";
import "node-forge/lib/pem";
import "node-forge/lib/pki";

let randomBytePool = "";
const FORGE_RANDOM_REFILL_BYTES = 4096;

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
 * 通过 Web Crypto 同步获取随机字节。
 *
 * @param {number} length 需要的字节长度
 * @returns {string|null} 随机字节串，当前运行环境不支持时返回 null
 */
function getWebCryptoRandomBytes(length) {
  const runtimeCrypto = getRuntimeGlobal()?.crypto;
  if (!runtimeCrypto?.getRandomValues) {
    return null;
  }
  const bytes = new Uint8Array(length);
  runtimeCrypto.getRandomValues(bytes);
  return uint8ArrayToBytes(bytes);
}

/**
 * 在 app-plus iOS 端通过原生 NSUUID 获取随机字节兜底。
 *
 * @param {number} length 需要的字节长度
 * @returns {string|null} 随机字节串，当前运行环境不支持时返回 null
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
      for (
        let index = 0;
        index < uuidText.length && randomBytes.length < length;
        index += 2
      ) {
        const byteValue = parseInt(uuidText.slice(index, index + 2), 16);
        if (isNaN(byteValue)) {
          return null;
        }
        randomBytes += String.fromCharCode(byteValue);
      }
    }
    return randomBytes;
  } catch (error) {
    return null;
  }
  // #endif
  return null;
}

/**
 * 在 app-plus Android 端通过原生 SecureRandom 获取随机字节兜底。
 *
 * @param {number} length 需要的字节长度
 * @returns {string|null} 随机字节串，当前运行环境不支持时返回 null
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
    return null;
  }
  // #endif
  return null;
}

/**
 * 在随机池不足时尝试同步补充一段新的随机字节。
 *
 * @param {number} length 当前至少需要的字节长度
 * @returns {void}
 */
function refillRandomBytePool(length) {
  const refillLength = Math.max(length, FORGE_RANDOM_REFILL_BYTES);
  const randomBytes =
    getWebCryptoRandomBytes(refillLength) ||
    getAppPlusAndroidRandomBytes(refillLength) ||
    getAppPlusIosRandomBytes(refillLength);
  if (randomBytes) {
    randomBytePool += randomBytes;
  }
}

/**
 * 从随机数池中按需提取字节串。
 *
 * @param {number} length 需要提取的字节长度
 * @returns {string} Forge 使用的二进制字符串
 */
function consumeRandomBytes(length) {
  if (randomBytePool.length < length) {
    refillRandomBytePool(length);
  }
  if (randomBytePool.length < length) {
    throw new Error("传输加密随机数池不足，且当前运行环境无法同步补充安全随机数");
  }
  const bytes = randomBytePool.slice(0, length);
  randomBytePool = randomBytePool.slice(length);
  return bytes;
}

forge.random.getBytesSync = function getBytesSync(length) {
  return consumeRandomBytes(length);
};

forge.random.getBytes = function getBytes(length, callback) {
  const bytes = consumeRandomBytes(length);
  if (typeof callback === "function") {
    callback(null, bytes);
  }
  return bytes;
};

/**
 * 向 Forge 随机数池预填充平台侧生成的随机字节。
 *
 * @param {string} bytes 待注入的二进制字符串
 * @returns {void}
 */
export function primeForgeRandomBytes(bytes) {
  randomBytePool += String(bytes || "");
}

export default forge;
