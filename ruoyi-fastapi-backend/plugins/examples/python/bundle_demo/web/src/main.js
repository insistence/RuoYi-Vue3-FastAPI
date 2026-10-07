import { createPluginClient } from '@ruoyi/plugin-bridge'
import './style.css'

// 统一按 ID 获取示例页面中的固定元素。
const element = (id) => document.getElementById(id)
let client
let context = {}
let transferController
let streamController
let lastEventId = ''

/** 逐条显示事件，保留游标供用户主动恢复，并限制页面中的历史数量。 */
async function receiveEvents() {
  if (streamController) return
  const controller = new AbortController()
  streamController = controller
  const start = element('start-stream')
  const stop = element('stop-stream')
  const status = element('stream-status')
  const list = element('stream-events')
  if (!lastEventId) list.replaceChildren()
  start.disabled = true
  stop.disabled = false
  status.textContent = '正在连接实时事件…'
  try {
    await client.stream(
      { path: 'events', params: { count: 10 }, lastEventId },
      {
        signal: controller.signal,
        onEvent: (event) => {
          const value = JSON.parse(event.data)
          lastEventId = event.id
          const item = document.createElement('li')
          item.textContent = `事件 ${value.index} / ${value.total} · ${value.serverTime}`
          list.append(item)
          while (list.children.length > 5) list.firstElementChild.remove()
          status.textContent = `已收到 ${value.index} / ${value.total} 条事件。`
        },
      }
    )
    status.textContent = '本次事件接收完成，可重新开始。'
    lastEventId = ''
  } catch (error) {
    status.textContent = controller.signal.aborted
      ? '已停止接收，可从上次位置继续。'
      : `${error.message}，可继续接收。`
  } finally {
    streamController = null
    start.textContent = lastEventId ? '继续接收' : '接收实时事件'
    start.disabled = false
    stop.disabled = true
  }
}
element('start-stream').addEventListener('click', receiveEvents)
element('stop-stream').addEventListener('click', () => streamController?.abort())

/**
 * 传输期间禁止重复提交，完成或失败后允许重试。
 */
async function transfer(kind) {
  if (transferController) return
  transferController = new AbortController()
  for (const id of ['upload', 'download', 'file']) element(id).disabled = true
  element('cancel-transfer').disabled = false
  const progress = element('file-progress')
  const resultElement = element('file-result')
  const controls = ['upload', 'download', 'file'].map(element)
  const cancelButton = element('cancel-transfer')
  progress.hidden = false
  progress.removeAttribute('value')
  resultElement.textContent = '正在传输…'
  const options = {
    signal: transferController.signal,
    onProgress: ({ loaded, total }) => {
      if (total) progress.value = Math.round((loaded * 100) / total)
      else progress.removeAttribute('value')
      resultElement.textContent = total
        ? `已传输 ${loaded} / ${total} 字节，等待服务端处理…`
        : `已传输 ${loaded} 字节，等待服务端处理…`
    },
  }
  try {
    if (kind === 'upload') {
      const file = element('file').files[0]
      if (!file) throw new Error('请先选择文件')
      const result = await client.upload({ path: 'files/inspect', file }, options)
      resultElement.textContent = `已检查 ${result.filename}（${result.size} 字节），SHA-256：${result.sha256}`
    } else {
      const blob = await client.download({ path: 'files/report' }, options)
      const url = URL.createObjectURL(blob)
      const link = Object.assign(document.createElement('a'), {
        href: url,
        download: 'plugin-report.csv',
      })
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      resultElement.textContent = `报表已接收（${blob.size} 字节），已交给浏览器保存。`
    }
    progress.value = 100
  } catch (error) {
    resultElement.textContent = error.message
    progress.hidden = true
  } finally {
    transferController = null
    for (const control of controls) control.disabled = false
    cancelButton.disabled = true
  }
}
element('file-form').addEventListener('submit', (event) => {
  event.preventDefault()
  transfer('upload')
})
element('download').addEventListener('click', () => transfer('download'))
element('cancel-transfer').addEventListener('click', () => transferController?.abort())

/**
 * 更新连接提示，并区分错误状态。
 */
const showNotice = (text, error = false) => {
  if (!element('notice')) return
  element('notice').textContent = text
  element('notice').classList.toggle('error', error)
}
/**
 * 同步请求忙碌状态与刷新按钮，供页面和辅助技术读取。
 */
const setBusy = (busy) => {
  element('workspace').setAttribute('aria-busy', String(busy))
  if (element('refresh')) element('refresh').disabled = busy
}
/**
 * 应用宿主推送的主题、语言、时区和插件内部路由。
 */
const applyContext = (next) => {
  context = { ...context, ...next }
  document.documentElement.dataset.theme = context.theme?.mode || 'light'
  document.documentElement.lang = context.language || 'zh-CN'
  element('time-zone').textContent = context.timeZone || 'UTC'
  const details = context.route === '/details'
  element('overview-panel').hidden = details
  element('details-panel').hidden = !details
  element('overview').setAttribute('aria-current', details ? 'false' : 'page')
  element('details').setAttribute('aria-current', details ? 'page' : 'false')
}
/**
 * 通过宿主桥接会话查询当前用户和服务端时间。
 */
const refresh = async () => {
  setBusy(true)
  try {
    const result = await client.request({ method: 'GET', path: 'summary' })
    element('user-name').textContent = result.userName
    element('server-time').textContent = new Intl.DateTimeFormat('zh-CN', {
      timeZone: context.timeZone || 'UTC',
      dateStyle: 'short',
      timeStyle: 'medium',
    }).format(new Date(result.serverTime))
    showNotice(result.greeting || '已连接管理平台，当前会话有效。')
  } catch (error) {
    showNotice(`${error.message}，可点击“刷新状态”重试。`, true)
  } finally {
    setBusy(false)
  }
}
element('refresh').addEventListener('click', refresh)
element('overview').addEventListener('click', () => client?.navigate('/'))
element('details').addEventListener('click', () => client?.navigate('/details'))
// POST 请求同样交给宿主桥接层处理身份和传输策略，页面不保存管理员 token。
element('echo-form').addEventListener('submit', async (event) => {
  event.preventDefault()
  const button = element('send')
  const result = element('echo-result')
  button.disabled = true
  result.textContent = '正在发送…'
  try {
    const response = await client.request({
      method: 'POST',
      path: 'echo',
      data: { message: element('message').value },
    })
    result.textContent = `服务端已收到：${response.message}`
  } catch (error) {
    result.textContent = error.message
  } finally {
    button.disabled = false
  }
})
/**
 * 建立宿主会话，并订阅偏好、路由、刷新和退出登录事件。
 */
async function connect() {
  try {
    const config = JSON.parse(element('ruoyi-plugin-config').textContent)
    client = createPluginClient({ pluginId: config.pluginId })
    client.subscribe(({ type, payload }) => {
      if (type === 'preferences' || type === 'route') applyContext(payload)
      if (type === 'refresh') refresh()
      if (type === 'logout') {
        transferController?.abort()
        streamController?.abort()
        element('workspace').replaceChildren(
          Object.assign(document.createElement('p'), {
            textContent: '登录已结束，请重新登录管理平台。',
          })
        )
      }
    })
    applyContext(await client.ready)
    await refresh()
  } catch (error) {
    showNotice(error.message || '请从管理平台打开插件页面。', true)
    setBusy(false)
    if (element('send')) element('send').disabled = true
  }
}
connect()
// 页面离开时释放桥接层的事件监听和待处理请求。
window.addEventListener('pagehide', () => client?.destroy(), { once: true })
