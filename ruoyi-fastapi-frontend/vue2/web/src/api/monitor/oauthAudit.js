import request from '@/utils/request'

// 查询认证审计列表
export function listOAuthAudit(query) {
  return request({
    url: '/monitor/oauth/audit/list',
    method: 'get',
    params: query,
  })
}
