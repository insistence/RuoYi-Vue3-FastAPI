// 任务调度同步状态
export const syncStates = {
  pending: { label: '待同步', type: 'warning' },
  applied: { label: '已生效', type: 'success' },
  failed: { label: '同步失败', type: 'danger' }
}

// 任务执行状态
export const executionStates = {
  pending: { label: '等待派发', type: 'info' },
  submitted: { label: '已派发', type: 'primary' },
  running: { label: '执行中', type: 'primary' },
  success: { label: '执行成功', type: 'success' },
  failed: { label: '执行失败', type: 'danger' },
  rejected: { label: '达到并发上限', type: 'warning' },
  missed: { label: '已过期', type: 'warning' },
  cancelled: { label: '已取消', type: 'info' },
  unknown: { label: '结果待确认', type: 'warning' }
}

/** 显示任务变更的提交及同步结果 */
export function notifyJobMutation(modal, response) {
  if (response.data?.syncStatus === 'failed') {
    modal.msgWarning(response.msg)
  } else if (response.data?.syncStatus === 'pending') {
    modal.msg(response.msg)
  } else {
    modal.msgSuccess(response.msg)
  }
}
