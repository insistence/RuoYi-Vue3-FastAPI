import { PLUGIN_BRIDGE_MAX_BYTES, PLUGIN_BRIDGE_MAX_STREAM_BYTES } from './pluginBridge.js'

/**
 * 增量读取 UTF-8 SSE，限制单条事件和总字节数，不缓存完整响应。
 * EOF 丢弃尚未以空行结束的事件；重连由调用方根据业务游标决定。
 *
 * @param {ReadableStream<Uint8Array>} body 响应字节流
 * @returns {AsyncGenerator<Object>} 按服务端顺序解析的事件
 */
export async function* readPluginSse(body) {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  const encoder = new TextEncoder()
  let total = 0
  let line = ''
  let skipLf = false
  let size = 0
  let data = []
  let event = ''
  let id = ''
  const consume = () => {
    size += encoder.encode(line).byteLength + 1
    if (size > PLUGIN_BRIDGE_MAX_BYTES) throw new Error('事件内容超过 64 KiB')
    if (!line) {
      const value = data.length ? { event: event || 'message', data: data.join('\n'), id } : null
      data = []
      event = ''
      size = 0
      return value
    }
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') data.push(value)
    if (field === 'event') event = value
    if (field === 'id' && !value.includes('\0')) id = value
    return null
  }
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) {
        decoder.decode()
        break
      }
      total += chunk.value.byteLength
      if (total > PLUGIN_BRIDGE_MAX_STREAM_BYTES) throw new Error('事件流超过 10 MiB')
      let text = decoder.decode(chunk.value, { stream: true })
      if (!text) continue
      if (skipLf && text.startsWith('\n')) text = text.slice(1)
      skipLf = text.endsWith('\r')
      let offset = 0
      for (const match of text.matchAll(/\r\n|\r|\n/g)) {
        line += text.slice(offset, match.index)
        const value = consume()
        line = ''
        offset = match.index + match[0].length
        if (value) yield value
      }
      line += text.slice(offset)
      if (size + encoder.encode(line).byteLength > PLUGIN_BRIDGE_MAX_BYTES)
        throw new Error('事件内容超过 64 KiB')
    }
  } finally {
    try {
      await reader.cancel()
    } finally {
      reader.releaseLock()
    }
  }
}

/**
 * 创建宿主专用 SSE 传输器；加密策略明确允许明文事件流时才发起请求。
 * Cookie 和 CSRF 仅由宿主发送，不暴露给插件消息。
 *
 * @param {Object} options 宿主策略、参数编码、时区和 fetch 依赖
 * @returns {Function} 接收受限配置并返回异步事件迭代器的函数
 */
export function createPluginSseTransport({
  loadPolicy,
  shouldEncryptRequest,
  serializeParams,
  getTimezone,
  fetchImpl = globalThis.fetch,
  origin = globalThis.location?.origin,
}) {
  return async function* ({ url, params, lastEventId, csrfToken, signal }) {
    const endpoint = new URL(url, origin)
    if (
      endpoint.origin !== origin ||
      !url.startsWith('/') ||
      url.startsWith('//') ||
      endpoint.search ||
      endpoint.hash
    )
      throw new Error('实时接口地址无效')
    const policy = await loadPolicy()
    if (shouldEncryptRequest({ url }, policy)) throw new Error('实时接口尚未配置传输策略例外')
    if (signal.aborted) throw new Error('实时连接已取消')
    endpoint.search = serializeParams(params || {})
    const response = await fetchImpl(endpoint.href, {
      method: 'GET',
      credentials: 'same-origin',
      redirect: 'error',
      cache: 'no-store',
      headers: {
        Accept: 'text/event-stream',
        'X-Plugin-CSRF': csrfToken,
        'X-Timezone': getTimezone(),
        ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
      },
      signal,
    })
    if (
      !response.ok ||
      response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !==
        'text/event-stream' ||
      !response.body
    ) {
      await response.body?.cancel()
      throw new Error('实时接口响应无效')
    }
    for await (const event of readPluginSse(response.body)) {
      if (event.event === 'ruoyi.plugin.closed') {
        const error = new Error('实时连接已由宿主关闭')
        error.name = 'PluginStreamClosedError'
        throw error
      }
      yield event
    }
  }
}
