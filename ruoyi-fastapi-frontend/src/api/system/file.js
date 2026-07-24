import request from '@/utils/request'

// 查询文件列表
export function listFile(query) {
  return request({
    url: '/system/file/list',
    method: 'get',
    params: query
  })
}

// 查询文件统计
export function getFileStats(query) {
  return request({
    url: '/system/file/stats',
    method: 'get',
    params: query
  })
}

// 查询文件业务保留策略
export function listFileRetentionPolicy() {
  return request({
    url: '/system/file/retention-policy/list',
    method: 'get'
  })
}

// 新增文件业务保留策略
export function addFileRetentionPolicy(data) {
  return request({
    url: '/system/file/retention-policy',
    method: 'post',
    data: data
  })
}

// 修改文件业务保留策略
export function updateFileRetentionPolicy(data) {
  return request({
    url: '/system/file/retention-policy',
    method: 'put',
    data: data
  })
}

// 删除文件业务保留策略
export function delFileRetentionPolicy(businessType) {
  return request({
    url: '/system/file/retention-policy/' + encodeURIComponent(businessType),
    method: 'delete'
  })
}

// 查询文件保留期限提醒
export function listFileRetentionReminder(query) {
  return request({
    url: '/system/file/retention-reminder/list',
    method: 'get',
    params: query
  })
}

// 执行文件保留期限提醒扫描
export function scanFileRetentionReminder() {
  return request({
    url: '/system/file/retention-reminder/scan',
    method: 'post'
  })
}

// 标记文件保留期限提醒为已读
export function readFileRetentionReminder(noticeIds) {
  return request({
    url: '/system/file/retention-reminder/' + noticeIds + '/read',
    method: 'put'
  })
}

// 查询文件详情
export function getFile(fileId) {
  return request({
    url: '/system/file/' + fileId,
    method: 'get'
  })
}

// 查询文件业务引用列表
export function listFileReference(fileId) {
  return request({
    url: '/system/file/' + fileId + '/reference/list',
    method: 'get'
  })
}

// 查询文件访问审计列表
export function listFileAccessLog(fileId, query) {
  return request({
    url: '/system/file/' + fileId + '/access-log/list',
    method: 'get',
    params: query
  })
}

// 查询文件访问控制列表
export function listFileAcl(fileId) {
  return request({
    url: '/system/file/' + fileId + '/acl/list',
    method: 'get'
  })
}

// 查询文件授权主体选项
export function searchFileAclSubjects(query) {
  return request({
    url: '/system/file/acl/subjects',
    method: 'get',
    params: query
  })
}

// 查询文件授权部门树
export function getFileAclDeptTree() {
  return request({
    url: '/system/file/acl/dept-tree',
    method: 'get'
  })
}

// 保存文件访问控制配置
export function saveFileAcl(fileId, data) {
  return request({
    url: '/system/file/' + fileId + '/acl',
    method: 'put',
    data: data
  })
}

// 批量保存文件访问控制配置
export function batchSaveFileAcl(data) {
  return request({
    url: '/system/file/acl/batch',
    method: 'put',
    data: data
  })
}

// 转移文件所有者和所属部门
export function transferFile(fileIds, data) {
  return request({
    url: '/system/file/' + fileIds + '/transfer',
    method: 'put',
    data: data
  })
}

// 恢复文件
export function restoreFile(fileIds) {
  return request({
    url: '/system/file/' + fileIds + '/restore',
    method: 'put'
  })
}

// 永久清理回收站文件
export function purgeFile(fileIds) {
  return request({
    url: '/system/file/purge/' + fileIds,
    method: 'delete'
  })
}

// 将文件移入回收站
export function delFile(fileIds) {
  return request({
    url: '/system/file/' + fileIds,
    method: 'delete'
  })
}
