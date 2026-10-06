import { createPluginClient } from '@ruoyi/plugin-bridge'
import './style.css'

// 统一按 ID 获取示例页面中的固定元素。
const element = (id) => document.getElementById(id)
let client
let context = {}

/**
 * 更新连接提示，并区分错误状态。
 */
const showNotice = (text, error = false) => {
  element('notice').textContent = text
  element('notice').classList.toggle('error', error)
}
/**
 * 同步请求忙碌状态与刷新按钮，供页面和辅助技术读取。
 */
const setBusy = (busy) => {
  element('workspace').setAttribute('aria-busy', String(busy))
  element('refresh').disabled = busy
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
    showNotice('已连接管理平台，当前会话有效。')
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
  element('send').disabled = true
  element('echo-result').textContent = '正在发送…'
  try {
    const response = await client.request({
      method: 'POST',
      path: 'echo',
      data: { message: element('message').value },
    })
    element('echo-result').textContent = `服务端已收到：${response.message}`
  } catch (error) {
    element('echo-result').textContent = error.message
  } finally {
    element('send').disabled = false
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
        element('workspace').replaceChildren(
          Object.assign(document.createElement('p'), {
            textContent: '登录已结束，请重新登录管理平台。',
          }),
        )
      }
    })
    applyContext(await client.ready)
    await refresh()
  } catch (error) {
    showNotice(error.message || '请从管理平台打开插件页面。', true)
    setBusy(false)
    element('send').disabled = true
  }
}
connect()
// 页面离开时释放桥接层的事件监听和待处理请求。
window.addEventListener('pagehide', () => client?.destroy(), { once: true })
