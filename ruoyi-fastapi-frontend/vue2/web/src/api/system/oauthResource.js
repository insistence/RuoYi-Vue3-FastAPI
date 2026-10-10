import request from '@/utils/request'

// 编码单个路径标识
const encodePathSegment = (value) => encodeURIComponent(String(value))
// 分别编码批量操作中的路径标识
const encodeBatchPath = (value) => String(value).split(',').map(encodePathSegment).join(',')

// 查询 OAuth 资源列表
export function listOAuthResources(query) {
  return request({
    url: '/system/oauth/resource/list',
    method: 'get',
    params: query,
  })
}

// 查询 OAuth 资源详情
export function getOAuthResource(resourceId) {
  return request({
    url: `/system/oauth/resource/${encodePathSegment(resourceId)}`,
    method: 'get',
  })
}

// 新增 OAuth 资源
export function addOAuthResource(data) {
  return request({
    url: '/system/oauth/resource',
    method: 'post',
    data,
  })
}

// 修改 OAuth 资源
export function updateOAuthResource(data) {
  return request({
    url: '/system/oauth/resource',
    method: 'put',
    data,
  })
}

// 删除 OAuth 资源
export function deleteOAuthResources(resourceIds) {
  return request({
    url: `/system/oauth/resource/${encodeBatchPath(resourceIds)}`,
    method: 'delete',
  })
}

// 修改 OAuth 资源状态
export function changeOAuthResourceStatus(data) {
  return request({
    url: '/system/oauth/resource/changeStatus',
    method: 'put',
    data,
  })
}

// 查询 OAuth Scope 列表
export function listOAuthScopes(query) {
  return request({
    url: '/system/oauth/scope/list',
    method: 'get',
    params: query,
  })
}

// 查询 OAuth Scope 详情
export function getOAuthScope(scopeCode) {
  return request({
    url: `/system/oauth/scope/${encodePathSegment(scopeCode)}`,
    method: 'get',
  })
}

// 新增 OAuth Scope
export function addOAuthScope(data) {
  return request({
    url: '/system/oauth/scope',
    method: 'post',
    data,
  })
}

// 修改 OAuth Scope
export function updateOAuthScope(data) {
  return request({
    url: '/system/oauth/scope',
    method: 'put',
    data,
  })
}

// 删除 OAuth Scope
export function deleteOAuthScopes(scopeCodes) {
  return request({
    url: `/system/oauth/scope/${encodeBatchPath(scopeCodes)}`,
    method: 'delete',
  })
}

// 修改 OAuth Scope 状态
export function changeOAuthScopeStatus(data) {
  return request({
    url: '/system/oauth/scope/changeStatus',
    method: 'put',
    data,
  })
}
