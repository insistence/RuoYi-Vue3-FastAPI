import { createPluginHostBridge, validatePluginSession } from '@ruoyi/plugin-bridge'
import { createMockTaskApi } from './mockRequest.js'

const element = (id) => document.getElementById(id)
const frame = element('plugin-frame')
const mock = createMockTaskApi({
  getDelay: () => element('delay').value,
  shouldFail: () => element('failure').checked,
  getCanWrite: () => !element('read-only').checked,
})
const bridge = createPluginHostBridge({
  pluginId: 'task_demo',
  session: validatePluginSession(
    {
      pluginId: 'task_demo',
      bridgeVersion: 1,
      uiBase: '/apps/task_demo/ui/',
      apiBase: '/apps/task_demo/api/',
      csrfToken: 'local-mock-session-no-credentials',
      expiresIn: 3600,
    },
    'task_demo'
  ),
  getTarget: () => frame.contentWindow,
  request: mock.request,
  getContext: () => ({
    theme: { mode: element('theme').value },
    language: 'zh-CN',
    timeZone: 'Asia/Shanghai',
    route: '/',
  }),
  onReady: () => {
    element('status').textContent = '模拟连接已建立'
  },
})
frame.src = '/index.html'
element('theme').addEventListener('change', () => bridge.updatePreferences())
element('read-only').addEventListener('change', () => bridge.refresh())
element('reload').addEventListener('click', () => frame.contentWindow.location.reload())
element('reset').addEventListener('click', () => {
  mock.reset()
  bridge.refresh()
})
element('empty').addEventListener('click', () => {
  mock.clear()
  bridge.refresh()
})
element('logout').addEventListener('click', () => {
  bridge.destroy({ logout: true })
  element('status').textContent = '模拟会话已退出；刷新整个页面可重新连接'
})
window.addEventListener('pagehide', () => bridge.destroy(), { once: true })
