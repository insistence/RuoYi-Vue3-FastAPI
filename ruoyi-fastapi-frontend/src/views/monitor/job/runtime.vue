<template>
  <el-dialog v-model="dialogVisible" title="任务运行记录" width="min(1140px, calc(100vw - 32px))" append-to-body>
    <el-tabs v-model="activeTab" @tab-change="resetPage">
      <el-tab-pane label="执行记录" name="executions" />
      <el-tab-pane label="同步状态" name="sync" />
    </el-tabs>
    <el-form inline @submit.prevent="resetPage">
      <el-form-item label="任务编号">
        <el-input-number v-model="queryJobId" :min="1" :precision="0" :controls="false" placeholder="全部任务" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" native-type="submit" :loading="loading">查询</el-button>
        <el-button icon="Refresh" :disabled="loading" @click="loadRecords()">刷新</el-button>
      </el-form-item>
    </el-form>
    <div v-if="focusedExecutionId && activeTab === 'executions'" class="execution-focus">
      <span>本次执行 ID：<code>{{ focusedExecutionId }}</code></span>
      <el-button link type="primary" @click="showAllExecutions">查看该任务全部记录</el-button>
    </div>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="runtime-alert" />
    <p class="runtime-status" role="status" aria-live="polite" aria-atomic="true">
      {{ loading ? '正在获取记录…' : `共 ${total} 条记录${processingCount ? `，当前页 ${processingCount} 条处理中` : ''}` }}
    </p>
    <el-table v-if="activeTab === 'executions'" v-loading="loading" :data="rows" row-key="executionId" max-height="460">
      <el-table-column type="expand">
        <template #default="scope">
          <div class="execution-details">
            <p><strong>执行 ID：</strong><code>{{ scope.row.executionId }}</code></p>
            <p><strong>完整结果：</strong>{{ scope.row.message || '尚无执行结果' }}</p>
            <p><strong>提交者：</strong>{{ scope.row.requestedBy || '系统调度' }}</p>
            <p><strong>计划时间：</strong>{{ parseTime(scope.row.scheduledTime) || '等待派发' }}</p>
            <p><strong>结束时间：</strong>{{ parseTime(scope.row.endTime) || '—' }}</p>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="jobId" label="任务编号" width="90" />
      <el-table-column prop="jobName" label="任务名称" min-width="150" show-overflow-tooltip />
      <el-table-column label="来源" width="75">
        <template #default="scope">{{ scope.row.source === 'manual' ? '手动' : '定时' }}</template>
      </el-table-column>
      <el-table-column label="执行状态" width="140">
        <template #default="scope">
          <el-tag :type="executionStates[scope.row.status]?.type || 'info'">
            {{ executionStates[scope.row.status]?.label || scope.row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="175">
        <template #default="scope">{{ parseTime(scope.row.createTime) }}</template>
      </el-table-column>
      <el-table-column label="耗时" width="105">
        <template #default="scope">{{ scope.row.runDurationMs == null ? '—' : `${scope.row.runDurationMs} 毫秒` }}</template>
      </el-table-column>
      <el-table-column prop="message" label="执行结果" min-width="230" show-overflow-tooltip />
    </el-table>
    <el-table v-else v-loading="loading" :data="rows" row-key="jobId" max-height="460">
      <el-table-column prop="jobId" label="任务编号" width="90" />
      <el-table-column label="配置类型" width="100">
        <template #default="scope">{{ scope.row.deleted ? '删除记录' : '任务配置' }}</template>
      </el-table-column>
      <el-table-column prop="configVersion" label="最新版本" width="95" />
      <el-table-column prop="appliedVersion" label="已应用版本" width="105" />
      <el-table-column label="同步状态" width="115">
        <template #default="scope">
          <el-tag :type="syncStates[scope.row.syncStatus]?.type || 'info'">
            {{ syncStates[scope.row.syncStatus]?.label || '待同步' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近生效时间" width="175">
        <template #default="scope">{{ parseTime(scope.row.appliedTime) || '—' }}</template>
      </el-table-column>
      <el-table-column prop="syncError" label="同步错误" min-width="240" show-overflow-tooltip />
      <el-table-column label="操作" width="100">
        <template #default="scope">
          <el-button v-if="scope.row.syncStatus !== 'applied'" v-hasPermi="['monitor:job:edit']" link type="primary"
            :loading="retryingId === scope.row.jobId" :disabled="retryingId !== null && retryingId !== scope.row.jobId"
            @click="retrySync(scope.row)">重试同步</el-button>
        </template>
      </el-table-column>
    </el-table>
    <pagination v-show="total > 0" :total="total" v-model:page="pageNum" v-model:limit="pageSize" @pagination="loadRecords()" />
    <template #footer>
      <el-button @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup name="JobRuntime">
import { listJobExecutions, listJobSync, retryJobSync } from '@/api/monitor/job'
import { executionStates, syncStates, notifyJobMutation } from './runtimeState'

const props = defineProps({
  visible: Boolean,
  initialTab: { type: String, default: 'executions' },
  jobId: { type: [Number, String], default: undefined },
  executionId: { type: String, default: undefined }
})
const emit = defineEmits(['update:visible', 'sync-updated'])
const { proxy } = getCurrentInstance()
const dialogVisible = computed({
  get: () => props.visible,
  set: value => emit('update:visible', value)
})
const activeTab = ref('executions')
const queryJobId = ref()
const focusedExecutionId = ref()
const rows = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const loadError = ref('')
const retryingId = ref(null)
let timer
let controller
let requestVersion = 0
const processingCount = computed(() => rows.value.filter(row => activeTab.value === 'executions'
  ? ['pending', 'submitted', 'running'].includes(row.status)
  : row.syncStatus === 'pending').length)

/** 停止自动刷新并取消未完成的请求 */
function stopRequests() {
  clearTimeout(timer)
  controller?.abort()
  requestVersion++
  loading.value = false
}

/** 根据执行和同步状态安排下一次刷新 */
function scheduleRefresh() {
  clearTimeout(timer)
  const needsRefresh = processingCount.value > 0 || loadError.value || (
    activeTab.value === 'sync' && rows.value.some(row => row.syncStatus === 'failed')
  )
  if (props.visible && !document.hidden && needsRefresh) {
    timer = setTimeout(() => loadRecords(true), 3000)
  }
}

/** 查询任务运行记录 */
async function loadRecords(silent = false) {
  if (!props.visible) return
  clearTimeout(timer)
  controller?.abort()
  controller = new AbortController()
  const version = ++requestVersion
  if (!silent) loading.value = true
  const query = {
    jobId: queryJobId.value || undefined,
    pageNum: pageNum.value,
    pageSize: pageSize.value
  }
  if (activeTab.value === 'executions' && focusedExecutionId.value) query.executionId = focusedExecutionId.value
  const fetchRecords = activeTab.value === 'executions' ? listJobExecutions : listJobSync
  try {
    const response = await fetchRecords(query, { signal: controller.signal, skipErrorMessage: true })
    if (version !== requestVersion || !props.visible) return
    rows.value = response.rows
    total.value = response.total
    loadError.value = ''
  } catch (error) {
    if (version === requestVersion && error.code !== 'ERR_CANCELED') {
      loadError.value = '获取记录失败，请刷新重试。'
    }
  } finally {
    if (version === requestVersion) {
      loading.value = false
      scheduleRefresh()
    }
  }
}

/** 重置分页并重新查询 */
function resetPage() {
  pageNum.value = 1
  rows.value = []
  total.value = 0
  loadRecords()
}

/** 查看当前任务的全部执行记录 */
function showAllExecutions() {
  focusedExecutionId.value = undefined
  resetPage()
}

/** 重试任务调度同步 */
async function retrySync(row) {
  retryingId.value = row.jobId
  try {
    const response = await retryJobSync(row.jobId)
    notifyJobMutation(proxy.$modal, response)
    emit('sync-updated')
    await loadRecords(true)
  } catch {
    // 请求层已显示重试失败原因，保留当前记录。
  } finally {
    retryingId.value = null
  }
}

/** 处理页面显示状态变化 */
function handleVisibility() {
  if (document.hidden) stopRequests()
  else if (props.visible) loadRecords(true)
}

watch(() => [props.visible, props.initialTab, props.jobId, props.executionId], () => {
  stopRequests()
  if (!props.visible) return
  activeTab.value = props.initialTab
  queryJobId.value = props.jobId == null ? undefined : Number(props.jobId)
  focusedExecutionId.value = props.executionId
  loadError.value = ''
  resetPage()
}, { immediate: true })

onMounted(() => document.addEventListener('visibilitychange', handleVisibility))
onDeactivated(() => {
  stopRequests()
  emit('update:visible', false)
})
onBeforeUnmount(() => {
  stopRequests()
  document.removeEventListener('visibilitychange', handleVisibility)
})
</script>

<style scoped>
.runtime-status {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
}

.runtime-alert {
  margin-bottom: 12px;
}

.execution-focus {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 12px;
}

.execution-details {
  padding: 4px 24px 12px;
  overflow-wrap: anywhere;
}

.execution-details p {
  margin: 8px 0;
  white-space: pre-wrap;
}

code {
  font-family: ui-monospace, Consolas, monospace;
  overflow-wrap: anywhere;
}
</style>
