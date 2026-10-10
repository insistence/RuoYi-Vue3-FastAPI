const RELEASE_STATUSES = {
  active: { label: '已生效', tagType: 'success' },
  disabled: { label: '已停用', tagType: 'info' },
  partial: { label: '部分生效', tagType: 'warning' },
  pending_restart: { label: '等待重启', tagType: 'warning' },
  failed: { label: '发布异常', tagType: 'danger' },
  no_target: { label: '未选择目标', tagType: 'info' },
}

const PREPARATION_LABELS = {
  idle: '尚未准备',
  preparing: '准备中',
  prepared: '准备完成',
  failed: '准备失败',
}

function workerCount(value) {
  return Number.isInteger(value) && value >= 0 ? String(value) : '未知'
}

/**
 * 将插件发布状态转换为列表和详情共用的展示信息。
 *
 * @param {Object} plugin 后端返回的插件信息
 * @returns {Object} 发布状态标签、进程统计和异常信息
 */
export function getPluginReleaseView(plugin = {}) {
  const release = plugin.release || {}
  const status = RELEASE_STATUSES[release.status] || { label: '状态未知', tagType: 'info' }
  const error = release.verificationError || release.lastError || ''
  return {
    ...status,
    label: release.verificationError ? '验证失败' : status.label,
    tagType: release.verificationError ? 'danger' : status.tagType,
    preparationLabel: PREPARATION_LABELS[release.prepareStatus] || '未知',
    workerSummary: `${plugin.enabled === '1' ? '已停用' : '已就绪'} ${workerCount(
      plugin.enabled === '1' ? release.disabledWorkers : release.healthyWorkers
    )} · 在线 ${workerCount(release.liveWorkers)} / 预期 ${workerCount(release.expectedWorkers)}`,
    counts: {
      healthy: workerCount(release.healthyWorkers),
      disabled: workerCount(release.disabledWorkers),
      mismatch: workerCount(release.mismatchWorkers),
      stale: workerCount(release.staleWorkers),
      missing: workerCount(release.missingWorkers),
      failed: workerCount(release.failedWorkers),
    },
    error,
    restartRequired: release.restartRequired === true,
    unavailable: !plugin.release,
  }
}
