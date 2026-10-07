import { createPluginHostBridge, validatePluginSession } from '@ruoyi/plugin-bridge'
import { createMockPluginRequest, createMockPluginStream } from './mockRequest.js'

const frame = document.getElementById('plugin-frame')
let route = '/'
const bridge = createPluginHostBridge({
  pluginId: 'bundle_demo',
  session: validatePluginSession(
    {
      pluginId: 'bundle_demo',
      bridgeVersion: 1,
      uiBase: '/apps/bundle_demo/ui/',
      apiBase: '/apps/bundle_demo/api/',
      csrfToken: 'local-mock-session-no-credentials',
      expiresIn: 3600,
    },
    'bundle_demo'
  ),
  getTarget: () => frame.contentWindow,
  request: createMockPluginRequest({
    getDelay: () => document.getElementById('delay').value,
    shouldFail: () => document.getElementById('failure').checked,
  }),
  stream: createMockPluginStream({
    getDelay: () => document.getElementById('delay').value,
    shouldFail: () => document.getElementById('failure').checked,
  }),
  getContext: () => ({
    theme: { mode: document.getElementById('theme').value },
    language: 'zh-CN',
    timeZone: 'Asia/Shanghai',
    route,
  }),
  onRoute: (value) => {
    route = value
    bridge.updateRoute(route)
  },
  onReady: () => {
    document.getElementById('status').textContent = '模拟连接已建立'
  },
})
frame.src = '/index.html'
document.getElementById('theme').addEventListener('change', () => bridge.updatePreferences())
document
  .getElementById('reload')
  .addEventListener('click', () => frame.contentWindow.location.reload())
document.getElementById('logout').addEventListener('click', () => {
  bridge.destroy({ logout: true })
  document.getElementById('status').textContent = '模拟会话已退出；刷新整个页面可重新连接'
})
window.addEventListener('pagehide', () => bridge.destroy(), { once: true })
