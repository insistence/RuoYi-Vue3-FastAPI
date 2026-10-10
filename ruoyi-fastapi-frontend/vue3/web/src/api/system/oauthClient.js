import request from '@/utils/request'

// 编码单个路径标识
const encodePathSegment = (value) => encodeURIComponent(String(value))
// 分别编码批量操作中的路径标识
const encodeBatchPath = (value) => String(value).split(',').map(encodePathSegment).join(',')

// 查询 OAuth 客户端列表
export function listOAuthClients(query) {
  return request({
    url: '/system/oauth/client/list',
    method: 'get',
    params: query,
  })
}

// 查询 OAuth 客户端详情
export function getOAuthClient(clientId) {
  return request({
    url: `/system/oauth/client/${encodePathSegment(clientId)}`,
    method: 'get',
  })
}

// 新增 OAuth 客户端
export function addOAuthClient(data) {
  return request({
    url: '/system/oauth/client',
    method: 'post',
    data,
  })
}

// 修改 OAuth 客户端
export function updateOAuthClient(data) {
  return request({
    url: '/system/oauth/client',
    method: 'put',
    data,
  })
}

// 删除 OAuth 客户端
export function deleteOAuthClients(clientIds) {
  return request({
    url: `/system/oauth/client/${encodeBatchPath(clientIds)}`,
    method: 'delete',
  })
}

// 修改 OAuth 客户端状态
export function changeOAuthClientStatus(data) {
  return request({
    url: '/system/oauth/client/changeStatus',
    method: 'put',
    data,
  })
}

// 轮换 OAuth 客户端密钥
export function rotateOAuthClientSecret(clientId, data = {}) {
  return request({
    url: `/system/oauth/client/${encodePathSegment(clientId)}/secret`,
    method: 'post',
    data,
  })
}

// 删除 OAuth 客户端密钥
export function revokeOAuthClientSecret(clientId, secretId) {
  return request({
    url: `/system/oauth/client/${encodePathSegment(clientId)}/secret/${encodePathSegment(secretId)}`,
    method: 'delete',
  })
}

// 新增 OAuth 客户端回调地址
export function addOAuthClientUri(clientId, data) {
  return request({
    url: `/system/oauth/client/${encodePathSegment(clientId)}/uri`,
    method: 'post',
    data,
  })
}

// 删除 OAuth 客户端回调地址
export function deleteOAuthClientUri(clientId, uriId) {
  return request({
    url: `/system/oauth/client/${encodePathSegment(clientId)}/uri/${encodePathSegment(uriId)}`,
    method: 'delete',
  })
}
