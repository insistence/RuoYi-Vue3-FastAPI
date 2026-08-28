import { completeInteraction } from '@/api/authCenter'
import { interactionRouteLocation, readInteractionCsrf, trustedCompletionUrl } from './interactionSecurity'

const ACTION_ROUTES = {
  login: '/auth-center/login',
  consent: '/auth-center/consent',
  changePassword: '/auth-center/change-password',
  error: '/auth-center/error'
}

export function useInteractionContext() {
  const route = useRoute()
  const router = useRouter()
  const interactionId = computed(() => String(route.query.interaction || ''))
  const storageKey = computed(() => `oidc:interaction:csrf:${interactionId.value}`)

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

  function csrfToken() {
    return interactionId.value ? sessionStorage.getItem(storageKey.value) || '' : ''
  }

  function clearInteraction() {
    if (interactionId.value) sessionStorage.removeItem(storageKey.value)
  }

  function goToAction(action) {
    const path = ACTION_ROUTES[action]
    if (!path || action === 'error') return
    return router.replace({ path, query: { interaction: interactionId.value } })
  }

  async function followServerRedirect(url) {
    if (!interactionId.value || typeof url !== 'string') {
      throw new Error('认证流程返回了无效跳转地址')
    }
    if (!trustedCompletionUrl(url, window.location.origin, interactionId.value)) {
      throw new Error('认证流程返回了不受信任的跳转地址')
    }
    const response = await completeInteraction(interactionId.value, csrfToken())
    const redirectUrl = response.data?.redirectUrl
    if (typeof redirectUrl !== 'string') throw new Error('认证流程返回了无效跳转地址')
    clearInteraction()
    window.location.assign(redirectUrl)
  }

  captureCsrfToken()

  return { interactionId, csrfToken, clearInteraction, goToAction, followServerRedirect }
}
