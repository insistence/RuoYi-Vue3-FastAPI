/**
 * 创建仅供本地开发的内存请求适配器，不发送网络请求或保存文件。
 *
 * @param {Object} options 延迟和故障注入选项
 * @returns {Function} 可传入宿主桥的异步请求函数
 */
export function createMockPluginRequest({ getDelay = () => 300, shouldFail = () => false } = {}) {
  const pause = (signal) =>
    new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(new Error('请求已取消'))
      const cancel = () => {
        clearTimeout(timer)
        reject(new Error('请求已取消'))
      }
      const timer = setTimeout(
        () => {
          signal?.removeEventListener('abort', cancel)
          resolve()
        },
        Math.max(0, Math.min(5000, Number(getDelay()) || 0))
      )
      signal?.addEventListener('abort', cancel, { once: true })
    })
  return async (config) => {
    const prefix = '/apps/bundle_demo/api/'
    if (!config.url.startsWith(prefix)) throw new Error('模拟宿主只处理当前插件 API')
    const path = config.url.slice(prefix.length)
    await pause(config.signal)
    if (shouldFail()) throw new Error('模拟接口失败')
    if (config.method === 'get' && path === 'summary') {
      return {
        pluginId: 'bundle_demo',
        userName: '本地模拟用户',
        serverTime: new Date().toISOString(),
        greeting: '本地模拟连接已就绪，文件仅在浏览器内处理。',
      }
    }
    if (config.method === 'post' && path === 'echo') {
      return {
        message: config.data.message,
        serverTime: new Date().toISOString(),
      }
    }
    if (config.method === 'post' && path === 'files/inspect') {
      const file = config.data.get('file')
      if (!(file instanceof Blob)) throw new Error('缺少文件')
      config.onUploadProgress?.({
        loaded: Math.floor(file.size / 2),
        total: file.size,
      })
      await pause(config.signal)
      config.onUploadProgress?.({ loaded: file.size, total: file.size })
      const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
      return {
        filename: file.name,
        size: file.size,
        sha256: Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, '0')
        ).join(''),
      }
    }
    if (config.method === 'get' && path === 'files/report') {
      const report = new Blob(['\uFEFFname,value\nmode,local-mock\n'], {
        type: 'text/csv;charset=utf-8',
      })
      config.onDownloadProgress?.({ loaded: report.size, total: report.size })
      return report
    }
    throw new Error('模拟接口未实现')
  }
}

/** 创建逐条产出事件的本地适配器，复用延迟和故障开关，支持取消与游标恢复。 */
export function createMockPluginStream({ getDelay = () => 300, shouldFail = () => false } = {}) {
  return async function* (config) {
    if (config.url !== '/apps/bundle_demo/api/events') throw new Error('模拟实时接口未实现')
    const count = Number(config.params?.count ?? 10)
    const cursorText = config.lastEventId || '0'
    const cursor = Number(cursorText)
    if (
      !Number.isInteger(count) ||
      count < 1 ||
      count > 20 ||
      !/^[0-9]{1,2}$/.test(cursorText) ||
      !Number.isInteger(cursor) ||
      cursor < 0 ||
      cursor > count
    )
      throw new Error('模拟事件参数无效')
    for (let index = cursor + 1; index <= count; index++) {
      await new Promise((resolve, reject) => {
        if (config.signal.aborted) return reject(new Error('已取消'))
        const cancel = () => {
          clearTimeout(timer)
          reject(new Error('已取消'))
        }
        const timer = setTimeout(
          () => {
            config.signal.removeEventListener('abort', cancel)
            resolve()
          },
          Math.max(100, Math.min(5000, Number(getDelay()) || 0))
        )
        config.signal.addEventListener('abort', cancel, { once: true })
      })
      if (shouldFail()) throw new Error('模拟实时接口失败')
      yield {
        event: 'tick',
        id: String(index),
        data: JSON.stringify({ index, total: count, serverTime: new Date().toISOString() }),
      }
    }
  }
}
