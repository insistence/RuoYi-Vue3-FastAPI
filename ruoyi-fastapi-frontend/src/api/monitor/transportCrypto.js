import request from '@/utils/request'

// 获取传输加密监控信息
export function getTransportCryptoMonitor() {
  return request({
    url: '/transport/crypto/monitor',
    method: 'get'
  })
}
