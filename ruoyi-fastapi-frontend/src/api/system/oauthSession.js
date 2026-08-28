import request from '@/utils/request'

const encodePathSegment = value => encodeURIComponent(String(value))
const encodeBatchPath = value => String(value).split(',').map(encodePathSegment).join(',')

// 查询 OAuth 会话列表
export function listOAuthSessions(query) {
  return request({
    url: '/system/oauth/session/list',
    method: 'get',
    params: query
  })
}

// 查询 OAuth 会话详情
export function getOAuthSession(sid) {
  return request({
    url: `/system/oauth/session/${encodePathSegment(sid)}`,
    method: 'get'
  })
}

// 撤销 OAuth 会话
export function revokeOAuthSessions(sids, data) {
  return request({
    url: `/system/oauth/session/${encodeBatchPath(sids)}`,
    method: 'delete',
    data
  })
}

// 按用户撤销 OAuth 会话
export function revokeUserOAuthSessions(userId, data) {
  return request({
    url: `/system/oauth/session/user/${encodePathSegment(userId)}`,
    method: 'delete',
    data
  })
}

// 查询 OAuth 授权列表
export function listOAuthGrants(query) {
  return request({
    url: '/system/oauth/grant/list',
    method: 'get',
    params: query
  })
}

// 查询 OAuth 授权详情
export function getOAuthGrant(grantId) {
  return request({
    url: `/system/oauth/grant/${encodePathSegment(grantId)}`,
    method: 'get'
  })
}

// 撤销 OAuth 授权
export function revokeOAuthGrants(grantIds, data) {
  return request({
    url: `/system/oauth/grant/${encodeBatchPath(grantIds)}`,
    method: 'delete',
    data
  })
}

// 查询 OIDC 签名密钥列表
export function listOidcKeys(query) {
  return request({
    url: '/system/oauth/key/list',
    method: 'get',
    params: query
  })
}

// 创建 OIDC 签名密钥轮换计划
export function rotateOidcKey(data) {
  return request({
    url: '/system/oauth/key/rotate',
    method: 'post',
    data
  })
}

// 激活 OIDC 签名密钥
export function activateOidcKey(kid) {
  return request({
    url: `/system/oauth/key/${encodePathSegment(kid)}/activate`,
    method: 'put'
  })
}

// 停止使用 OIDC 签名密钥
export function retireOidcKey(kid) {
  return request({
    url: `/system/oauth/key/${encodePathSegment(kid)}/retire`,
    method: 'put'
  })
}

// 删除 OIDC 签名密钥
export function deleteOidcKey(kid) {
  return request({
    url: `/system/oauth/key/${encodePathSegment(kid)}`,
    method: 'delete'
  })
}
