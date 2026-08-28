import request from '@/utils/request'

const encodePathSegment = value => encodeURIComponent(String(value))

const interactionHeaders = csrfToken => ({
  isToken: false,
  repeatSubmit: false,
  ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {})
})

const issuerRequest = config => request({ baseURL: '', ...config })

// 查询认证交互状态
export function getInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}`,
    method: 'get',
    headers: interactionHeaders(csrfToken)
  })
}

// 查询认证验证码
export function getInteractionCaptcha(interactionId) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/captcha`,
    method: 'get',
    headers: interactionHeaders()
  })
}

// 提交认证登录
export function submitInteractionLogin(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/login`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data
  })
}

// 提交密码更新
export function submitInteractionPasswordChange(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/change-password`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data
  })
}

// 提交授权确认
export function submitInteractionConsent(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/consent`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data
  })
}

// 取消认证交互
export function cancelInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/cancel`,
    method: 'post',
    headers: interactionHeaders(csrfToken)
  })
}

// 完成交互并取得已经绑定的外部跳转地址
export function completeInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/complete`,
    method: 'post',
    headers: interactionHeaders(csrfToken)
  })
}
