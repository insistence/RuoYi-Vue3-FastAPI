import { completeInteraction } from '@/api/authCenter'
import {
  interactionRouteLocation,
  readInteractionCsrf,
  trustedCompletionUrl,
} from './interactionSecurity'

const ACTION_ROUTES = {
  login: '/auth-center/login',
  consent: '/auth-center/consent',
  changePassword: '/auth-center/change-password',
  error: '/auth-center/error',
}

/**
 * 创建认证页面共享的交互上下文。
 *
 * @returns {Object} 交互标识、CSRF凭据及页面跳转方法
 */
export function useInteractionContext() {
  const route = useRoute()
  const router = useRouter()
  const interactionId = computed(() => String(route.query.interaction || ''))
  const storageKey = computed(() => `oidc:interaction:csrf:${interactionId.value}`)

  /**
   * 保存地址片段中的CSRF凭据并移除片段。
   */
  function captureCsrfToken() {
    const token = readInteractionCsrf(window.location.hash)
    if (token && interactionId.value) {
      sessionStorage.setItem(storageKey.value, token)
      window.history.replaceState(
        window.history.state,
        '',
        interactionRouteLocation(route.path, interactionId.value)
      )
    }
  }

  /**
   * 读取当前认证交互的CSRF凭据。
   *
   * @returns {string} 当前交互的CSRF凭据
   */
  function csrfToken() {
    return interactionId.value ? sessionStorage.getItem(storageKey.value) || '' : ''
  }

  /**
   * 清除当前交互保存在会话存储中的凭据。
   */
  function clearInteraction() {
    if (interactionId.value) {
      sessionStorage.removeItem(storageKey.value)
    }
  }

  /**
   * 跳转到服务端指定的下一步认证页面。
   *
   * @param {string} action 下一步认证动作
   * @returns {Promise|undefined} 路由跳转结果，无有效目标时返回undefined
   */
  function goToAction(action) {
    if (action === 'redirect') {
      return followServerRedirect(
        `/auth/interaction/${encodeURIComponent(interactionId.value)}/complete`
      )
    }
    const path = ACTION_ROUTES[action]
    if (!path || action === 'error') {
      return
    }
    return router.replace({ path, query: { interaction: interactionId.value } })
  }

  /**
   * 完成可信认证交互后跳转到服务端绑定的应用地址。
   *
   * @param {string} url 当前交互的同源完成地址
   * @returns {Promise<void>} 交互完成并发起跳转
   * @throws {Error} 交互标识或完成地址无效
   */
  async function followServerRedirect(url) {
    if (!interactionId.value || typeof url !== 'string') {
      throw new Error('认证流程返回了无效跳转地址')
    }
    if (!trustedCompletionUrl(url, window.location.origin, interactionId.value)) {
      throw new Error('认证流程返回了不受信任的跳转地址')
    }
    const response = await completeInteraction(interactionId.value, csrfToken())
    const redirectUrl = response.data?.redirectUrl
    if (typeof redirectUrl !== 'string') {
      throw new Error('认证流程返回了无效跳转地址')
    }
    clearInteraction()
    window.location.assign(redirectUrl)
  }

  captureCsrfToken()

  return {
    interactionId,
    csrfToken,
    clearInteraction,
    goToAction,
    followServerRedirect,
  }
}
