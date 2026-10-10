import request from '@/utils/request'

// 编码单个路径标识
const encodePathSegment = (value) => encodeURIComponent(String(value))

// 构造认证交互请求头
const interactionHeaders = (csrfToken) => ({
  isToken: false,
  repeatSubmit: false,
  ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
})

// 使用认证中心根路径发送协议交互请求
const issuerRequest = (config) => request({ baseURL: '', ...config })

// 通过常规 API 前缀读取公开功能状态，不需要交互或管理后台凭据。
export function getAuthCenterStatus() {
  return request({
    url: '/auth/status',
    method: 'get',
    headers: interactionHeaders(),
    timeout: 5000,
    skipErrorMessage: true,
  })
}

// 查询认证交互状态
export function getInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}`,
    method: 'get',
    headers: interactionHeaders(csrfToken),
  })
}

// 查询认证验证码
export function getInteractionCaptcha(interactionId) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/captcha`,
    method: 'get',
    headers: interactionHeaders(),
  })
}

// 提交认证登录
export function submitInteractionLogin(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/login`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data,
  })
}

// 提交密码更新
export function submitInteractionPasswordChange(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/change-password`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data,
  })
}

// 提交授权确认
export function submitInteractionConsent(interactionId, csrfToken, data) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/consent`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
    data,
  })
}

// 取消认证交互
export function cancelInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/cancel`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
  })
}

// 完成交互并取得已经绑定的外部跳转地址
export function completeInteraction(interactionId, csrfToken) {
  return issuerRequest({
    url: `/auth/interaction/${encodePathSegment(interactionId)}/complete`,
    method: 'post',
    headers: interactionHeaders(csrfToken),
  })
}
