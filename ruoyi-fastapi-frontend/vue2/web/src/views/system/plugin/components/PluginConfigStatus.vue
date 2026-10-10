<template>
  <section
    class="config-status"
    aria-label="配置生效状态"
    :aria-busy="loading"
  >
    <div class="config-status-toolbar">
      <strong>配置生效状态</strong>
      <el-button
        type="text"
        :loading="loading"
        @click="refresh"
        >刷新状态</el-button
      >
    </div>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-else-if="loading && !data"
      role="status"
    >
      正在查询配置版本…
    </p>
    <template v-else-if="data">
      <el-alert
        :title="statusText"
        :type="statusType"
        :closable="false"
        show-icon
      />
      <p class="config-status-help">
        {{
          data.scope === 'reporting_workers'
            ? '仅统计已上报进程'
            : data.scope === 'current_worker'
              ? '当前查询仅有本进程数据'
              : '当前尚无可用的进程数据'
        }}。 启动快照在重启后更新；插件主动读取最新配置时，由插件负责应用。
        <template v-if="data.sampleIntervalSeconds"
          >远程状态每 {{ data.sampleIntervalSeconds }} 秒上报。</template
        >
      </p>
      <p
        v-if="
          data.unknownWorkers ||
          data.invalidSnapshots ||
          data.staleSnapshots ||
          data.workerLimitReached
        "
        class="config-status-help"
      >
        部分进程版本尚不能确认：{{ data.unknownWorkers || 0 }} 个未上报配置版本，
        {{ data.invalidSnapshots || 0 }} 个无效采样，{{ data.staleSnapshots || 0 }} 个过期采样。
        <template v-if="data.workerLimitReached">本次查询已达到进程采样上限。</template>
      </p>
      <details>
        <summary>查看配置版本与进程明细</summary>
        <p class="config-revision">已保存版本：{{ data.desiredRevision }}</p>
        <ul
          v-if="(data.workers || []).length"
          class="config-workers"
        >
          <li
            v-for="worker in data.workers"
            :key="worker.workerId"
          >
            <p class="config-revision">进程 {{ worker.workerId }} · 插件 {{ worker.version }}</p>
            <p>
              {{
                !worker.active
                  ? '尚未激活'
                  : worker.matchesDesired
                    ? '启动快照匹配'
                    : '启动快照待重启更新'
              }}
            </p>
            <p class="config-revision">启动版本：{{ worker.startupRevision }}</p>
            <p
              v-if="worker.lastReadRevision"
              class="config-revision"
            >
              最近按需读取：{{ worker.lastReadRevision }}（不表示业务已应用）
            </p>
          </li>
        </ul>
        <p v-else>尚未观测到支持配置版本上报的进程。</p>
      </details>
    </template>
  </section>
</template>

<script setup name="PluginConfigStatus">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getPluginConfigStatus } from '@/api/system/plugin'

const props = defineProps({
  pluginId: { type: String, required: true },
  refreshKey: { type: Number, default: 0 },
})
const data = ref(null)
const loading = ref(false)
const error = ref('')
let revision = 0
let controller
const statusText = computed(() => {
  if (data.value?.state === 'restart_required')
    return `${data.value.pendingWorkers} 个已观测进程的启动配置待重启更新`
  if (data.value?.state === 'observed_match')
    return `${data.value.matchedWorkers} 个已观测进程的启动配置与保存版本匹配`
  return '尚未观测到运行中的启动配置版本，请确认插件已启用并完成启动'
})
const statusType = computed(() => (data.value?.state === 'restart_required' ? 'warning' : 'info'))

async function refresh() {
  const current = ++revision
  controller?.abort()
  controller = new AbortController()
  error.value = ''
  loading.value = true
  try {
    const response = await getPluginConfigStatus(props.pluginId, controller.signal)
    if (current === revision) data.value = response.data
  } catch {
    if (current === revision) {
      data.value = null
      error.value = '配置状态查询失败，已保存内容不受影响，可刷新重试。'
    }
  } finally {
    if (current === revision) loading.value = false
  }
}
watch(
  () => [props.pluginId, props.refreshKey],
  () => {
    data.value = null
    refresh()
  },
  { immediate: true }
)
onBeforeUnmount(() => {
  revision++
  controller?.abort()
})
</script>

<style scoped>
.config-status {
  margin-bottom: 24px;
  color: var(--el-text-color-regular, #606266);
  line-height: 1.6;
}
.config-status-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.config-status-help {
  margin: 10px 0;
  font-size: 13px;
}
.config-revision {
  font-family: monospace;
  overflow-wrap: anywhere;
  font-size: 13px;
}
.config-workers {
  padding-left: 20px;
}
.config-workers li + li {
  margin-top: 12px;
}
summary {
  cursor: pointer;
  color: var(--el-color-primary, var(--current-color, #409eff));
  padding: 8px 0;
}
</style>
