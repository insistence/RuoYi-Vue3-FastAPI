/**
 * 插件通信桥 v1，不依赖 Vue 或 axios，可复制到独立打包的插件中使用。
 * 同源 iframe 中运行的是受信任代码，不提供安全沙箱隔离。
 */
export const PLUGIN_BRIDGE_NAMESPACE = 'ruoyi.plugin'
export const PLUGIN_BRIDGE_VERSION = 1
export const PLUGIN_BRIDGE_MAX_BYTES = 64 * 1024
export const PLUGIN_BRIDGE_MAX_PENDING = 8
export const PLUGIN_BRIDGE_MAX_FILE_BYTES = 10 * 1024 * 1024
const REQUEST_TIMEOUT = 15000
const TRANSFER_TIMEOUT = 120000
const ID_PATTERN = /^[a-z][a-z0-9_-]{1,63}$/
const MESSAGE_ID_PATTERN = /^[a-zA-Z0-9_-]{1,80}$/
const METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])
const isRecord = (value) =>
  value !== null &&
  typeof value === 'object' &&
  (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)

function assertKeys(value, keys) {
  if (!isRecord(value) || Object.keys(value).some((key) => !keys.includes(key))) {
    throw new Error('插件消息格式无效')
  }
}

function jsonCopy(value, limit = PLUGIN_BRIDGE_MAX_BYTES) {
  let nodes = 0
  const visit = (item, depth) => {
    nodes += 1
    if (nodes > 8192) throw new Error('插件消息过大')
    if (depth > 20) throw new Error('插件消息嵌套过深')
    if (typeof item === 'string' && item.length > limit) throw new Error('插件消息过大')
    if (item === null || typeof item === 'boolean' || typeof item === 'string') return
    if (typeof item === 'number' && Number.isFinite(item)) return
    if (Array.isArray(item)) return item.forEach((child) => visit(child, depth + 1))
    if (!isRecord(item)) throw new Error('插件消息必须为 JSON')
    for (const [key, child] of Object.entries(item)) {
      if (['__proto__', 'prototype', 'constructor'].includes(key)) {
        throw new Error('插件消息字段无效')
      }
      visit(child, depth + 1)
    }
  }
  visit(value, 0)
  const text = JSON.stringify(value)
  if (new TextEncoder().encode(text).length > limit) throw new Error('插件消息过大')
  return JSON.parse(text)
}

export function validatePluginId(pluginId) {
  if (typeof pluginId !== 'string' || !ID_PATTERN.test(pluginId)) {
    throw new Error('插件标识无效')
  }
  return pluginId
}

export function normalizePluginBase(base = '') {
  if (typeof base !== 'string') throw new Error('插件部署路径无效')
  if (base === '' || base === '/') return ''
  const normalized = base.replace(/\/$/, '')
  if (!/^\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(normalized)) {
    throw new Error('插件部署路径无效')
  }
  return normalized
}

/**
 * 校验插件会话，只接受包含已知部署前缀的当前插件路径。
 *
 * @param {Object} value 后端返回的会话信息
 * @param {string} pluginId 当前插件标识
 * @param {string} base 插件部署前缀
 * @param {number} now 当前时间戳，单位为毫秒
 * @returns {Object} 包含过期时间的会话信息
 */
export function validatePluginSession(value, pluginId, base = '', now = Date.now()) {
  validatePluginId(pluginId)
  const prefix = `${normalizePluginBase(base)}/apps/${pluginId}`
  if (
    !isRecord(value) ||
    value.pluginId !== pluginId ||
    value.bridgeVersion !== PLUGIN_BRIDGE_VERSION ||
    value.uiBase !== `${prefix}/ui/` ||
    value.apiBase !== `${prefix}/api/` ||
    typeof value.csrfToken !== 'string' ||
    !/^[a-zA-Z0-9_-]{16,256}$/.test(value.csrfToken) ||
    !Number.isInteger(value.expiresIn) ||
    value.expiresIn < 1 ||
    value.expiresIn > 3600
  ) {
    throw new Error('插件会话信息无效')
  }
  return { ...value, expiresAt: now + value.expiresIn * 1000 }
}

/**
 * 校验相对于 apiBase 的接口路径，查询参数统一通过 params 传递。
 *
 * @param {string} path 插件接口相对路径
 * @returns {string} 校验后的路径
 */
export function validatePluginApiPath(path) {
  if (typeof path !== 'string' || path.length > 1024) throw new Error('插件接口路径无效')
  if (path === '') return path
  if (
    !/^[a-zA-Z0-9_.~-]+(?:\/[a-zA-Z0-9_.~-]+)*\/?$/.test(path) ||
    path.split('/').some((segment) => segment === '.' || segment === '..')
  ) {
    throw new Error('插件接口路径无效')
  }
  return path
}

export function validatePluginRoute(route) {
  if (
    typeof route !== 'string' ||
    route.length > 1024 ||
    !/^\/(?:[a-zA-Z0-9_.~-]+\/?)*$/.test(route) ||
    route.split('/').some((segment) => segment === '.' || segment === '..')
  ) {
    throw new Error('插件页面路径无效')
  }
  return route
}

function nonce() {
  return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, '0')
  ).join('')
}

function envelope(pluginId, type, instance, payload, id) {
  return {
    namespace: PLUGIN_BRIDGE_NAMESPACE,
    version: PLUGIN_BRIDGE_VERSION,
    pluginId,
    type,
    instance,
    ...(payload === undefined ? {} : { payload }),
    ...(id === undefined ? {} : { id }),
  }
}

function validEnvelope(event, origin, source, pluginId) {
  const value = event.data
  return (
    event.origin === origin &&
    event.source === source &&
    isRecord(value) &&
    value.namespace === PLUGIN_BRIDGE_NAMESPACE &&
    value.version === PLUGIN_BRIDGE_VERSION &&
    value.pluginId === pluginId &&
    Object.keys(value).every((key) =>
      ['namespace', 'version', 'pluginId', 'type', 'instance', 'payload', 'id'].includes(key)
    )
  )
}

function validateRequest(payload) {
  assertKeys(payload, ['method', 'path', 'params', 'data'])
  if (!METHODS.has(payload.method)) throw new Error('插件请求方法无效')
  validatePluginApiPath(payload.path)
  if (payload.params !== undefined && !isRecord(payload.params)) {
    throw new Error('插件查询参数无效')
  }
  if (['GET', 'HEAD'].includes(payload.method) && payload.data !== undefined) {
    throw new Error('该请求方法不能携带请求体')
  }
  return jsonCopy(payload)
}

function validateTransfer(type, payload) {
  if (type === 'download') return validateRequest(payload)
  assertKeys(payload, ['method', 'path', 'params', 'file', 'fieldName', 'filename', 'fields'])
  const { file, ...metadata } = payload
  const safe = jsonCopy(metadata)
  validateRequest({
    method: safe.method,
    path: safe.path,
    ...(safe.params === undefined ? {} : { params: safe.params }),
  })
  if (!['POST', 'PUT', 'PATCH'].includes(safe.method)) throw new Error('文件上传方法无效')
  if (!(file instanceof Blob) || file.size > PLUGIN_BRIDGE_MAX_FILE_BYTES) {
    throw new Error('文件必须是 Blob 或 File，且不能超过 10 MiB')
  }
  if (!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(safe.fieldName)) throw new Error('文件字段名无效')
  if (
    typeof safe.filename !== 'string' ||
    !safe.filename.trim() ||
    safe.filename.length > 255 ||
    /[\\/\x00-\x1f\x7f]/.test(safe.filename) ||
    ['.', '..'].includes(safe.filename)
  )
    throw new Error('上传文件名无效')
  if (
    !isRecord(safe.fields) ||
    Object.entries(safe.fields).some(
      ([key, value]) =>
        !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(key) ||
        key === safe.fieldName ||
        typeof value !== 'string'
    )
  )
    throw new Error('上传表单字段无效')
  return { ...safe, file }
}

async function validateDownload(data) {
  if (!(data instanceof Blob) || data.size > PLUGIN_BRIDGE_MAX_FILE_BYTES) {
    throw new Error('下载文件无效或超过 10 MiB')
  }
  // 错误响应不能作为文件交付；合法的 JSON 文件仍可下载。
  if (
    data.size <= PLUGIN_BRIDGE_MAX_BYTES &&
    /(?:application\/json|\+json)(?:;|$)/i.test(data.type)
  ) {
    let value
    try {
      value = JSON.parse(await data.text())
    } catch {
      /* 非 JSON 内容按文件返回。 */
    }
    if (isRecord(value) && typeof value.code === 'number' && value.code !== 200) {
      throw new Error('插件下载失败')
    }
  }
  return data
}

/**
 * 创建宿主侧通信桥，复用现有请求客户端转发插件请求。
 * getTarget 必须返回当前 iframe 的 contentWindow，不能返回全局窗口或旧页面缓存。
 *
 * @param {Object} options 宿主桥配置，包括会话、请求客户端和事件回调
 * @returns {Object} 会话更新、偏好同步、刷新和销毁方法
 */
export function createPluginHostBridge({
  pluginId,
  session,
  getTarget,
  request,
  getContext = () => ({}),
  onReady = () => {},
  onRoute = () => {},
  onDisconnect = () => {},
  eventTarget = globalThis.window,
  origin = globalThis.location?.origin,
  now = Date.now,
  timeoutMs = REQUEST_TIMEOUT,
  transferTimeoutMs = TRANSFER_TIMEOUT,
}) {
  validatePluginId(pluginId)
  const target = getTarget()
  if (!target || !origin || origin === 'null') throw new Error('插件页面尚未就绪')
  let currentSession = session
  let instance = nonce()
  let clientId = null
  let destroyed = false
  const retiredClients = new Set()
  const pending = new Map()
  const live = () => !destroyed && getTarget() === target && now() < currentSession.expiresAt
  const send = (type, payload, id) => {
    if (live()) target.postMessage(envelope(pluginId, type, instance, payload, id), origin)
  }
  const cancelPending = () => {
    for (const entry of pending.values()) {
      clearTimeout(entry.timer)
      entry.controller.abort()
    }
    pending.clear()
  }
  const resultError = (id, message) => send('result', { ok: false, message }, id)

  const listener = (event) => {
    if (!live() || !validEnvelope(event, origin, target, pluginId)) return
    const message = event.data
    if (message.type === 'ready') {
      if (
        message.instance !== '' ||
        message.id !== undefined ||
        !isRecord(message.payload) ||
        Object.keys(message.payload).length !== 1 ||
        !MESSAGE_ID_PATTERN.test(message.payload.clientId || '') ||
        retiredClients.has(message.payload.clientId)
      )
        return
      if (clientId !== null && clientId !== message.payload.clientId) {
        // 页面导航会保留 WindowProxy，但新文档使用新的 clientId 和 instance。
        // 拒绝旧文档迟到的 ready 消息，避免恢复已经失效的连接。
        if (retiredClients.size >= 1024) {
          destroyed = true
          cancelPending()
          eventTarget.removeEventListener('message', listener)
          onDisconnect('插件页面重载次数过多，请重新加载')
          return
        }
        retiredClients.add(clientId)
        cancelPending()
        instance = nonce()
      }
      clientId = message.payload.clientId
      send('initialize', {
        ...jsonCopy(getContext()),
        clientId,
        uiBase: currentSession.uiBase,
        apiBase: currentSession.apiBase,
        capabilities: { files: { version: 1, maxBytes: PLUGIN_BRIDGE_MAX_FILE_BYTES } },
      })
      onReady()
      return
    }
    if (clientId === null || message.instance !== instance) return
    if (message.type === 'route') {
      try {
        assertKeys(message.payload, ['route'])
        if (message.id !== undefined) return
        onRoute(validatePluginRoute(message.payload.route))
      } catch {
        // 忽略无效的页面导航消息。
      }
      return
    }
    if (!MESSAGE_ID_PATTERN.test(message.id || '')) return
    if (message.type === 'cancel') {
      const entry = pending.get(message.id)
      if (entry) {
        clearTimeout(entry.timer)
        entry.controller.abort()
        pending.delete(message.id)
      }
      return
    }
    if (!['request', 'upload', 'download'].includes(message.type) || pending.has(message.id)) return
    if (pending.size >= PLUGIN_BRIDGE_MAX_PENDING) {
      resultError(message.id, '插件请求过多，请稍后重试')
      return
    }
    let payload
    try {
      payload =
        message.type === 'request'
          ? validateRequest(message.payload)
          : validateTransfer(message.type, message.payload)
    } catch (error) {
      resultError(message.id, error.message)
      return
    }
    const controller = new AbortController()
    const entry = { controller, timer: null }
    const duration = message.type === 'request' ? timeoutMs : transferTimeoutMs
    entry.timer = setTimeout(() => {
      if (pending.get(message.id) !== entry) return
      pending.delete(message.id)
      controller.abort()
      resultError(message.id, '插件请求超时，请重试')
    }, duration)
    pending.set(message.id, entry)
    const progressState = new Map()
    const progress = (phase) => (event) => {
      if (pending.get(message.id) !== entry || !live()) return
      const loaded = Number(event.loaded)
      if (!Number.isSafeInteger(loaded) || loaded < 0) return
      if (phase === 'download' && loaded > PLUGIN_BRIDGE_MAX_FILE_BYTES) {
        pending.delete(message.id)
        clearTimeout(entry.timer)
        controller.abort()
        resultError(message.id, '下载文件超过 10 MiB')
        return
      }
      const total = Number.isSafeInteger(event.total) && event.total >= loaded ? event.total : null
      const previous = progressState.get(phase)
      if (
        previous &&
        (loaded < previous.loaded || (now() - previous.time < 100 && loaded !== total))
      )
        return
      progressState.set(phase, { loaded, time: now() })
      send('progress', { phase, loaded, total }, message.id)
    }
    Promise.resolve()
      .then(() => {
        if (!live() || pending.get(message.id) !== entry) return undefined
        let body = payload.data
        if (message.type === 'upload') {
          body = new FormData()
          for (const [key, value] of Object.entries(payload.fields)) body.append(key, value)
          body.append(payload.fieldName, payload.file, payload.filename)
        }
        return request({
          url: currentSession.apiBase + payload.path,
          baseURL: '',
          method: payload.method.toLowerCase(),
          ...(payload.params === undefined ? {} : { params: payload.params }),
          ...(body === undefined ? {} : { data: body }),
          headers: {
            isToken: false,
            'X-Plugin-CSRF': currentSession.csrfToken,
            repeatSubmit: false,
            ...(message.type === 'request' ? {} : { encrypt: false, encryptResponse: false }),
            ...(message.type === 'upload' ? { 'Content-Type': undefined } : {}),
          },
          signal: controller.signal,
          timeout: duration,
          skipErrorMessage: true,
          pluginBridge: true,
          ...(message.type === 'upload' ? { onUploadProgress: progress('upload') } : {}),
          ...(message.type === 'download'
            ? { responseType: 'blob', onDownloadProgress: progress('download') }
            : {}),
        })
      })
      .then(async (data) => {
        if (pending.get(message.id) === entry && live()) {
          const safeData =
            message.type === 'download' ? await validateDownload(data) : jsonCopy(data)
          if (pending.get(message.id) === entry && live())
            send('result', { ok: true, data: safeData }, message.id)
        }
      })
      .catch(() => {
        // 只返回可展示的错误信息，避免向插件暴露请求头、调用堆栈或宿主令牌。
        if (pending.get(message.id) === entry) resultError(message.id, '插件请求失败，请重试')
      })
      .finally(() => {
        clearTimeout(entry.timer)
        if (pending.get(message.id) === entry) pending.delete(message.id)
      })
  }
  eventTarget.addEventListener('message', listener)
  return {
    setSession(nextSession) {
      if (
        nextSession.pluginId !== pluginId ||
        nextSession.apiBase !== currentSession.apiBase ||
        nextSession.uiBase !== currentSession.uiBase
      )
        throw new Error('插件会话路径发生变化')
      currentSession = nextSession
    },
    updatePreferences() {
      if (clientId) send('preferences', jsonCopy(getContext()))
    },
    updateRoute(route) {
      if (clientId) send('route', { route: validatePluginRoute(route) })
    },
    refresh() {
      if (clientId) send('refresh', {})
    },
    destroy({ logout = false } = {}) {
      if (logout && !destroyed && getTarget() === target) {
        target.postMessage(envelope(pluginId, 'logout', instance, {}), origin)
      }
      destroyed = true
      instance = ''
      cancelPending()
      eventTarget.removeEventListener('message', listener)
    },
  }
}

/**
 * 创建子页面 SDK，握手完成后可通过宿主请求当前插件接口。
 * request 保留宿主请求客户端返回的 JSON；标准接口仍返回 { code, data, msg }。
 *
 * @param {Object} options 子页面配置，包括插件标识和通信超时时间
 * @returns {Object} 握手状态、请求、导航、事件订阅和销毁方法
 * @example
 * const client = createPluginClient({ pluginId: 'demo' })
 * await client.ready
 * await client.request({ method: 'GET', path: 'status' })
 */
export function createPluginClient({
  pluginId,
  eventTarget = globalThis.window,
  parentWindow = globalThis.window?.parent,
  origin = globalThis.location?.origin,
  timeoutMs = REQUEST_TIMEOUT,
  transferTimeoutMs = TRANSFER_TIMEOUT,
}) {
  validatePluginId(pluginId)
  if (!parentWindow || parentWindow === eventTarget || !origin || origin === 'null') {
    throw new Error('请从管理平台打开插件页面')
  }
  const clientId = nonce()
  let instance = ''
  let destroyed = false
  let context = null
  let waitingForReady = 0
  let resolveReady
  let rejectReady
  const subscribers = new Set()
  const pending = new Map()
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve
    rejectReady = reject
  })
  // 调用方可能在模块初始化后才注册异常处理，先接住握手失败的拒绝状态。
  ready.catch(() => {})
  const waitForReady = (signal) => {
    if (!signal) return ready
    if (signal.aborted) return Promise.reject(new Error('插件请求已取消'))
    return new Promise((resolve, reject) => {
      const cancel = () => {
        signal.removeEventListener('abort', cancel)
        reject(new Error('插件请求已取消'))
      }
      signal.addEventListener('abort', cancel, { once: true })
      ready.then(
        (value) => {
          signal.removeEventListener('abort', cancel)
          resolve(value)
        },
        (error) => {
          signal.removeEventListener('abort', cancel)
          reject(error)
        }
      )
    })
  }
  const send = (type, payload, id) => {
    if (!destroyed)
      parentWindow.postMessage(envelope(pluginId, type, instance, payload, id), origin)
  }
  const notify = (type, payload) => {
    for (const subscriber of subscribers) {
      try {
        subscriber({ type, payload })
      } catch {
        // 插件回调异常不能阻止退出登录或连接清理。
      }
    }
  }
  const destroy = (message = '插件连接已关闭') => {
    if (destroyed) return
    for (const [id, entry] of pending) {
      send('cancel', undefined, id)
      clearTimeout(entry.timer)
      entry.cleanup()
      entry.reject(new Error(message))
    }
    pending.clear()
    destroyed = true
    clearTimeout(readyTimer)
    rejectReady(new Error(message))
    eventTarget.removeEventListener('message', listener)
    subscribers.clear()
  }
  const listener = (event) => {
    if (destroyed || !validEnvelope(event, origin, parentWindow, pluginId)) return
    const message = event.data
    if (message.type === 'initialize') {
      if (
        context !== null ||
        !MESSAGE_ID_PATTERN.test(message.instance || '') ||
        !isRecord(message.payload) ||
        message.payload.clientId !== clientId
      )
        return
      instance = message.instance
      context = jsonCopy(message.payload)
      clearTimeout(readyTimer)
      resolveReady(context)
      notify('initialize', context)
      return
    }
    if (!instance || message.instance !== instance) return
    if (message.type === 'progress') {
      const entry = pending.get(message.id)
      const value = message.payload
      if (
        !entry?.onProgress ||
        !isRecord(value) ||
        !['upload', 'download'].includes(value.phase) ||
        !Number.isSafeInteger(value.loaded) ||
        value.loaded < 0 ||
        !(
          value.total === null ||
          (Number.isSafeInteger(value.total) && value.total >= value.loaded)
        )
      )
        return
      try {
        entry.onProgress({ phase: value.phase, loaded: value.loaded, total: value.total })
      } catch {
        /* 不影响请求完成。 */
      }
      return
    }
    if (message.type === 'result') {
      const entry = pending.get(message.id)
      if (!entry || !isRecord(message.payload) || typeof message.payload.ok !== 'boolean') return
      pending.delete(message.id)
      clearTimeout(entry.timer)
      entry.cleanup()
      if (message.payload.ok) {
        try {
          const data = message.payload.data
          if (entry.type === 'download') {
            if (!(data instanceof Blob) || data.size > PLUGIN_BRIDGE_MAX_FILE_BYTES)
              throw new Error('下载文件无效')
            entry.resolve(data)
          } else entry.resolve(jsonCopy(data))
        } catch (error) {
          entry.reject(error)
        }
      } else
        entry.reject(
          new Error(
            typeof message.payload.message === 'string'
              ? message.payload.message.slice(0, 200)
              : '插件请求失败'
          )
        )
      return
    }
    if (['preferences', 'route', 'refresh', 'logout'].includes(message.type)) {
      if (message.type === 'preferences') context = { ...context, ...jsonCopy(message.payload) }
      if (message.type === 'route')
        context = { ...context, route: validatePluginRoute(message.payload?.route) }
      notify(message.type, message.payload)
      if (message.type === 'logout') destroy('登录状态已失效')
    }
  }
  eventTarget.addEventListener('message', listener)
  const readyTimer = setTimeout(() => destroy('插件初始化超时，请重试'), timeoutMs)
  send('ready', { clientId })
  const execute = async (type, safePayload, { signal, onProgress } = {}) => {
    if (onProgress !== undefined && typeof onProgress !== 'function')
      throw new Error('进度回调无效')
    if (destroyed || signal?.aborted) throw new Error('插件请求已取消')
    if (pending.size + waitingForReady >= PLUGIN_BRIDGE_MAX_PENDING) {
      throw new Error('插件请求过多，请稍后重试')
    }
    waitingForReady += 1
    try {
      await waitForReady(signal)
    } finally {
      waitingForReady -= 1
    }
    if (destroyed || signal?.aborted) throw new Error('插件请求已取消')
    if (type !== 'request' && context.capabilities?.files?.version !== 1) {
      throw new Error('当前宿主不支持文件传输，请升级宿主')
    }
    if (pending.size >= PLUGIN_BRIDGE_MAX_PENDING) throw new Error('插件请求过多，请稍后重试')
    const id = nonce()
    return new Promise((resolve, reject) => {
      const cancel = () => {
        const entry = pending.get(id)
        if (!entry) return
        pending.delete(id)
        clearTimeout(entry.timer)
        entry.cleanup()
        send('cancel', undefined, id)
        reject(new Error('插件请求已取消或超时'))
      }
      const timer = setTimeout(cancel, type === 'request' ? timeoutMs : transferTimeoutMs)
      pending.set(id, {
        type,
        onProgress,
        resolve,
        reject,
        timer,
        cleanup: () => signal?.removeEventListener('abort', cancel),
      })
      signal?.addEventListener('abort', cancel, { once: true })
      send(type, safePayload, id)
    })
  }
  return {
    ready,
    get context() {
      return context
    },
    async request(payload, options) {
      return execute('request', validateRequest(payload), options)
    },
    async upload(payload, options) {
      const value = {
        method: 'POST',
        fieldName: 'file',
        fields: {},
        filename: payload?.file?.name || 'upload.bin',
        ...payload,
      }
      return execute('upload', validateTransfer('upload', value), options)
    },
    async download(payload, options) {
      return execute(
        'download',
        validateTransfer('download', { method: 'GET', ...payload }),
        options
      )
    },
    navigate(route) {
      if (!instance || destroyed) throw new Error('插件尚未连接')
      send('route', { route: validatePluginRoute(route) })
    },
    subscribe(handler) {
      if (typeof handler !== 'function') throw new Error('事件订阅无效')
      subscribers.add(handler)
      return () => subscribers.delete(handler)
    },
    destroy,
  }
}
