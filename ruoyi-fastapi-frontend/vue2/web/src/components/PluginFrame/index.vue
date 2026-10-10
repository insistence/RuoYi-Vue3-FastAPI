<template>
  <section
    v-loading="loading"
    class="plugin-frame"
    :aria-busy="loading"
    element-loading-text="正在加载插件，请稍候…"
  >
    <el-result
      v-if="error"
      icon="warning"
      title="插件暂时无法打开"
      :sub-title="error"
      role="alert"
    >
      <template #extra>
        <el-button
          type="primary"
          :disabled="!userStore.token"
          @click="openPlugin"
          >重新加载</el-button
        >
      </template>
    </el-result>
    <template v-else>
      <div class="plugin-frame__toolbar">
        <span>{{ title }}</span>
        <el-button
          size="small"
          :disabled="loading || !frameSrc"
          @click="refreshPlugin"
          >刷新插件</el-button
        >
      </div>
      <iframe
        v-if="frameSrc"
        ref="frameRef"
        :key="frameKey"
        :src="frameSrc"
        :title="title"
        class="plugin-frame__content"
        referrerpolicy="same-origin"
        @error="fail('插件页面加载失败，请重试')"
      />
    </template>
  </section>
</template>

<script setup name="PluginFrame">
import {
  computed,
  getCurrentInstance,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from 'vue'
import request from '@/utils/request'
import { getDisplayTimezone } from '@/utils/time'
import { tansParams } from '@/utils/ruoyi'
import { createPluginSseTransport } from '@/utils/pluginSse'
import {
  ensureTransportCryptoPolicyLoaded,
  shouldEncryptRequest,
} from '@/utils/transportCryptoPolicy'
import {
  createPluginHostBridge,
  normalizePluginBase,
  validatePluginId,
  validatePluginRoute,
  validatePluginSession,
} from '@/utils/pluginBridge'

const { proxy } = getCurrentInstance()
const route = computed(() => proxy.$route)
const router = proxy.$router
const userStore = proxy.$store.state.user
const settingsStore = proxy.$store.state.settings
const frameRef = ref(null)
const frameSrc = ref('')
const frameKey = ref(0)
const loading = ref(false)
const error = ref('')
const title = computed(() => String(route.value.meta.title || '插件应用'))
let bridge = null
let session = null
let generation = 0
let active = false
let renewalTimer = null
let expiryTimer = null
let handshakeTimer = null
let sessionRequest = null

function preferences() {
  return {
    theme: {
      mode:
        document.documentElement.classList.contains('dark') ||
        document.documentElement.getAttribute('data-theme') === 'dark'
          ? 'dark'
          : 'light',
      primary: settingsStore.theme,
    },
    language: document.documentElement.lang || 'zh-CN',
    timeZone: getDisplayTimezone(),
  }
}

function currentPluginRoute() {
  try {
    return validatePluginRoute(route.value.query.pluginRoute || '/')
  } catch {
    return '/'
  }
}

function cleanup(logout = false) {
  generation += 1
  clearTimeout(renewalTimer)
  clearTimeout(expiryTimer)
  clearTimeout(handshakeTimer)
  sessionRequest?.abort()
  sessionRequest = null
  bridge?.destroy({ logout })
  bridge = null
  session = null
  frameSrc.value = ''
  loading.value = false
}

function fail(message) {
  cleanup()
  error.value = message
}

function scheduleRenewal(ticket) {
  clearTimeout(renewalTimer)
  clearTimeout(expiryTimer)
  const remaining = session.expiresAt - Date.now()
  // 续期请求挂起或标签页休眠时，仍按会话过期时间销毁页面。
  expiryTimer = setTimeout(
    () => {
      if (ticket === generation) fail('插件会话已过期，请重新加载')
    },
    Math.max(0, remaining)
  )
  renewalTimer = setTimeout(
    () => {
      if (ticket === generation) void loadSession(ticket, true)
    },
    Math.max(500, remaining - Math.min(30000, remaining / 5))
  )
}

async function loadSession(ticket, renew = false) {
  const controller = new AbortController()
  sessionRequest = controller
  try {
    const pluginId = validatePluginId(route.value.meta.pluginId)
    const base = normalizePluginBase(process.env.VUE_APP_PLUGIN_BASE || '')
    const response = await request({
      url: `${base}/plugin/runtime/${pluginId}/session`,
      baseURL: '',
      method: 'post',
      headers: { repeatSubmit: false },
      signal: controller.signal,
      skipErrorMessage: true,
      pluginBridge: true,
    })
    if (!active || ticket !== generation || !userStore.token || controller.signal.aborted) return
    const nextSession = validatePluginSession(response.data, pluginId, base)
    if (renew) {
      if (!session || session.expiresAt <= Date.now()) throw new Error('插件会话已过期')
      bridge?.setSession(nextSession)
      session = nextSession
    } else {
      session = nextSession
      frameKey.value += 1
      // 创建 iframe 后立即注册监听，确保能收到子页面的 ready 消息。
      frameSrc.value = session.uiBase
      await nextTick()
      if (!active || ticket !== generation || !frameRef.value) return
      bridge = createPluginHostBridge({
        pluginId,
        session,
        getTarget: () => frameRef.value?.contentWindow,
        request,
        stream: createPluginSseTransport({
          loadPolicy: ensureTransportCryptoPolicyLoaded,
          shouldEncryptRequest,
          serializeParams: tansParams,
          getTimezone: getDisplayTimezone,
        }),
        getContext: () => ({ ...preferences(), route: currentPluginRoute() }),
        onReady: () => {
          if (ticket !== generation) return
          clearTimeout(handshakeTimer)
          loading.value = false
        },
        onDisconnect: fail,
        onRoute: (pluginRoute) => {
          if (ticket !== generation || pluginRoute === currentPluginRoute()) return
          // Vue Router 3 通过失败回调处理重复或被取消的导航，避免遗留未处理的 Promise。
          router.replace(
            { path: route.value.path, query: { ...route.value.query, pluginRoute } },
            () => {},
            () => {}
          )
        },
      })
      handshakeTimer = setTimeout(() => {
        if (ticket === generation) fail('插件连接超时，请重新加载')
      }, 15000)
    }
    scheduleRenewal(ticket)
  } catch {
    if (ticket === generation && !controller.signal.aborted) {
      fail(renew ? '插件会话续期失败，请重新加载' : '无法建立插件会话，请确认权限后重试')
    }
  } finally {
    if (sessionRequest === controller) sessionRequest = null
  }
}

function openPlugin() {
  cleanup()
  error.value = ''
  if (!active) return
  if (!userStore.token) {
    error.value = '登录状态已失效，请重新登录'
    return
  }
  loading.value = true
  void loadSession(generation)
}

function refreshPlugin() {
  bridge?.refresh()
}

watch([() => route.value.meta.pluginId, () => userStore.token], () => {
  if (!userStore.token) {
    cleanup(true)
    error.value = '登录状态已失效，请重新登录'
  } else if (active) openPlugin()
})
watch(preferences, () => bridge?.updatePreferences())
watch(
  () => route.value.query.pluginRoute,
  () => bridge?.updateRoute(currentPluginRoute())
)

// Vue 2 宿主主题和语言还可能由 DOM 切换，同步这些非响应式偏好。
let languageObserver
function activate() {
  if (active) return
  active = true
  languageObserver = new MutationObserver(() => bridge?.updatePreferences())
  languageObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['lang', 'class', 'data-theme'],
  })
  openPlugin()
}
function deactivate() {
  active = false
  languageObserver?.disconnect()
  cleanup()
}
onMounted(activate)
onActivated(activate)
onDeactivated(deactivate)
onBeforeUnmount(deactivate)
</script>

<style scoped>
.plugin-frame {
  min-height: 360px;
  height: calc(100vh - 130px);
  height: calc(100dvh - 130px);
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color, #fff);
}
.plugin-frame__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 16px;
  color: var(--el-text-color-regular, #606266);
  border-bottom: 1px solid var(--el-border-color-lighter, #f2f6fc);
}
.plugin-frame__toolbar span {
  overflow-wrap: anywhere;
}
.plugin-frame__content {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 0;
}
</style>
