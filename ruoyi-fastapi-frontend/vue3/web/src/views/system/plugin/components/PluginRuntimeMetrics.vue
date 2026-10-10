<template>
  <section
    v-loading="loading"
    class="plugin-metrics"
    aria-label="插件运行观测"
    :aria-busy="loading"
  >
    <div class="metrics-toolbar">
      <span role="status">{{
        updatedAt ? `查询时间：${updatedAt}` : '查询实际运行进程的累计指标'
      }}</span>
      <el-button
        icon="Refresh"
        :loading="loading"
        @click="refresh"
        >刷新指标</el-button
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
    />
    <template v-else-if="data">
      <el-alert
        v-if="data.supported !== false"
        :title="
          data.scope === 'reporting_workers'
            ? `已上报进程：${data.observedWorkers} 个`
            : '当前仅显示接收本次请求的进程'
        "
        :type="data.scope === 'reporting_workers' ? 'info' : 'warning'"
        description="指标从进程启动后累计，重启会归零；已上报进程不代表全部预期进程。"
        show-icon
        :closable="false"
      />
      <p
        v-if="data.supported !== false"
        class="metrics-hint"
      >
        采样间隔 {{ data.sampleIntervalSeconds || '-' }} 秒，有效期
        {{ data.sampleTtlSeconds || '-' }} 秒。 耗时包含完整请求或任务，P95 为直方图估算上界。
      </p>
      <el-alert
        v-if="
          data.workerLimitReached || data.invalidSnapshots || data.staleSnapshots || droppedSeries
        "
        title="部分采样未纳入统计"
        :description="`无效 ${data.invalidSnapshots || 0}，过期 ${data.staleSnapshots || 0}，超出指标容量 ${droppedSeries}；进程读取上限${data.workerLimitReached ? '已达到' : '未达到'}。`"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-empty
        v-if="!data.series?.length"
        :description="
          data.supported === false
            ? '当前进程未启用运行观测'
            : '暂无该插件的运行指标，仅支持已加载的 v2 插件'
        "
      />
      <article
        v-for="row in data.series || []"
        :key="[row.version, row.digest, row.generation, row.operation].join(':')"
        class="metrics-record"
      >
        <div class="metrics-record-title">
          <strong>{{ row.operation }}</strong
          ><el-tag effect="plain">{{ row.version }}</el-tag>
        </div>
        <dl class="metrics-values">
          <div
            v-for="item in counters(row)"
            :key="item.label"
          >
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
        <details>
          <summary>版本身份与最近异常</summary>
          <dl class="metrics-identities">
            <dt>制品摘要</dt>
            <dd>{{ row.digest || '源码插件' }}</dd>
            <dt>发布代际</dt>
            <dd>{{ row.generation || '-' }}</dd>
            <dt>最近异常</dt>
            <dd>{{ row.lastErrorType || '-' }}</dd>
            <dt>追踪标识</dt>
            <dd>{{ row.lastErrorRequestId || '-' }}</dd>
          </dl>
        </details>
      </article>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { getPluginRuntimeMetrics } from '@/api/system/plugin'

const props = defineProps({ pluginId: { type: String, default: '' } })
const data = ref(null)
const loading = ref(false)
const error = ref('')
const updatedAt = ref('')
let controller
let revision = 0
const droppedSeries = computed(() =>
  (data.value?.workers || []).reduce((total, worker) => total + (worker.droppedSeries || 0), 0)
)

/** 查询当前插件，取消旧请求并丢弃迟到响应。 */
async function refresh() {
  controller?.abort()
  const current = ++revision
  loading.value = false
  error.value = ''
  if (!props.pluginId) return
  controller = new AbortController()
  loading.value = true
  try {
    const response = await getPluginRuntimeMetrics(props.pluginId, controller.signal)
    if (current !== revision) return
    data.value = response.data
    updatedAt.value = new Date().toLocaleTimeString()
  } catch {
    if (current === revision) error.value = '运行指标查询失败，请重试。'
  } finally {
    if (current === revision) loading.value = false
  }
}

/** 将同一版本的调用计数与耗时展示为带文字标签的指标。 */
function counters(row) {
  return [
    { label: '调用', value: row.started },
    { label: '在途', value: row.active },
    { label: '成功', value: row.succeeded },
    { label: '拒绝', value: row.rejected },
    { label: '失败 / 失败率', value: `${row.failed} / ${row.failureRatePercent}%` },
    { label: '取消', value: row.cancelled },
    { label: '超时（计入失败）', value: row.timedOut },
    { label: '平均耗时', value: `${row.averageDurationMs} ms` },
    { label: 'P95 估算上界', value: `${row.p95UpperBoundMs} ms` },
    { label: '最大耗时', value: `${Number(row.durationMaxMs).toFixed(1)} ms` },
  ]
}

watch(
  () => props.pluginId,
  () => {
    data.value = null
    updatedAt.value = ''
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
.plugin-metrics {
  min-height: 160px;
}
.metrics-toolbar,
.metrics-record-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.metrics-hint {
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.metrics-record {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
}
.metrics-record-title {
  justify-content: flex-start;
}
.metrics-values {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 16px;
}
.metrics-values dt {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.metrics-values dd {
  margin: 4px 0 0;
  font-size: 18px;
  font-variant-numeric: tabular-nums;
}
summary {
  cursor: pointer;
  padding: 8px 0;
  color: var(--el-color-primary);
}
.metrics-identities {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 8px;
}
.metrics-identities dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-family: monospace;
}
</style>
