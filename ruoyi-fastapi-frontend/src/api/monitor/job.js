import request from '@/utils/request'

// 预览定时任务执行时刻
export function previewJob(data, signal) {
  return request({
    url: '/monitor/job/preview',
    method: 'post',
    data,
    signal,
    skipErrorMessage: true,
    headers: { repeatSubmit: false }
  })
}

// 查询定时任务调度列表
export function listJob(query, options = {}) {
  return request({
    url: '/monitor/job/list',
    method: 'get',
    params: query,
    ...options
  })
}

// 查询定时任务调度详细
export function getJob(jobId) {
  return request({
    url: '/monitor/job/' + jobId,
    method: 'get'
  })
}

// 新增定时任务调度
export function addJob(data) {
  return request({
    url: '/monitor/job',
    method: 'post',
    data: data
  })
}

// 修改定时任务调度
export function updateJob(data) {
  return request({
    url: '/monitor/job',
    method: 'put',
    data: data
  })
}

// 删除定时任务调度
export function delJob(jobId) {
  return request({
    url: '/monitor/job/' + jobId,
    method: 'delete'
  })
}

// 任务状态修改
export function changeJobStatus(jobId, status) {
  const data = {
    jobId,
    status
  }
  return request({
    url: '/monitor/job/changeStatus',
    method: 'put',
    data: data
  })
}


// 定时任务立即执行一次
export function runJob(jobId) {
  const data = {
    jobId
  }
  return request({
    url: '/monitor/job/run',
    method: 'put',
    data: data
  })
}

// 查询独立执行请求和执行结果
export function listJobExecutions(query, options = {}) {
  return request({
    url: '/monitor/job/execution/list',
    method: 'get',
    params: query,
    ...options
  })
}

// 查询定时任务执行结果
export function getJobExecution(executionId, options = {}) {
  return request({
    url: '/monitor/job/execution/' + executionId,
    method: 'get',
    ...options
  })
}

// 查询同步状态，包括已删除任务的同步记录
export function listJobSync(query, options = {}) {
  return request({
    url: '/monitor/job/sync/list',
    method: 'get',
    params: query,
    ...options
  })
}

// 重试定时任务调度同步
export function retryJobSync(jobId) {
  return request({
    url: '/monitor/job/sync/' + jobId,
    method: 'post'
  })
}
