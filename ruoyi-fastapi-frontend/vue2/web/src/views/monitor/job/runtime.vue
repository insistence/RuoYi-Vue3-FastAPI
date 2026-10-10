<template>
  <el-dialog
    :visible.sync="dialogVisible"
    title="任务运行记录"
    width="1000px"
    append-to-body
  >
    <el-tabs
      v-model="activeTab"
      @tab-click="resetPage"
    >
      <el-tab-pane
        label="执行记录"
        name="executions"
      />
      <el-tab-pane
        label="同步状态"
        name="sync"
      />
    </el-tabs>
    <el-form
      size="small"
      :inline="true"
      label-width="68px"
      @submit.native.prevent="resetPage"
    >
      <el-form-item label="任务编号">
        <el-input-number
          v-model="queryJobId"
          :min="1"
          :precision="0"
          :controls="false"
          placeholder="全部任务"
          style="width: 240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button
          size="mini"
          type="primary"
          icon="el-icon-search"
          native-type="submit"
          :loading="loading"
          >查询</el-button
        >
        <el-button
          size="mini"
          icon="el-icon-refresh"
          :disabled="loading"
          @click="loadRecords()"
          >刷新</el-button
        >
      </el-form-item>
    </el-form>
    <div
      v-if="focusedExecutionId && activeTab === 'executions'"
      class="execution-focus"
    >
      <span
        >本次执行 ID：<code>{{ focusedExecutionId }}</code></span
      >
      <el-button
        size="mini"
        type="text"
        @click="showAllExecutions"
        >查看该任务全部记录</el-button
      >
    </div>
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
      class="runtime-alert"
    />
    <p
      class="runtime-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      {{
        loading
          ? '正在获取记录…'
          : `共 ${total} 条记录${processingCount ? `，当前页 ${processingCount} 条处理中` : ''}`
      }}
    </p>
    <el-table
      v-if="activeTab === 'executions'"
      v-loading="loading"
      :data="rows"
      row-key="executionId"
      max-height="460"
    >
      <el-table-column type="expand">
        <template slot-scope="scope">
          <div class="execution-details">
            <p>
              <strong>执行 ID：</strong><code>{{ scope.row.executionId }}</code>
            </p>
            <p><strong>完整结果：</strong>{{ scope.row.message || '尚无执行结果' }}</p>
            <p><strong>提交者：</strong>{{ scope.row.requestedBy || '系统调度' }}</p>
            <p><strong>计划时间：</strong>{{ parseTime(scope.row.scheduledTime) || '等待派发' }}</p>
            <p><strong>结束时间：</strong>{{ parseTime(scope.row.endTime) || '—' }}</p>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        align="center"
        prop="jobId"
        label="任务编号"
        width="90"
      />
      <el-table-column
        align="center"
        prop="jobName"
        label="任务名称"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column
        align="center"
        label="来源"
        width="75"
      >
        <template slot-scope="scope">{{
          scope.row.source === 'manual' ? '手动' : '定时'
        }}</template>
      </el-table-column>
      <el-table-column
        align="center"
        label="执行状态"
        width="140"
      >
        <template slot-scope="scope">
          <el-tag
            size="small"
            :type="executionStates[scope.row.status]?.type || 'info'"
          >
            {{ executionStates[scope.row.status]?.label || scope.row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        align="center"
        label="提交时间"
        width="175"
      >
        <template slot-scope="scope">{{ parseTime(scope.row.createTime) }}</template>
      </el-table-column>
      <el-table-column
        align="center"
        label="耗时"
        width="105"
      >
        <template slot-scope="scope">{{
          scope.row.runDurationMs == null ? '—' : `${scope.row.runDurationMs} 毫秒`
        }}</template>
      </el-table-column>
      <el-table-column
        align="center"
        prop="message"
        label="执行结果"
        min-width="230"
        show-overflow-tooltip
      />
    </el-table>
    <el-table
      v-else
      v-loading="loading"
      :data="rows"
      row-key="jobId"
      max-height="460"
    >
      <el-table-column
        align="center"
        prop="jobId"
        label="任务编号"
        width="90"
      />
      <el-table-column
        align="center"
        label="配置类型"
        width="100"
      >
        <template slot-scope="scope">{{ scope.row.deleted ? '删除记录' : '任务配置' }}</template>
      </el-table-column>
      <el-table-column
        align="center"
        prop="configVersion"
        label="最新版本"
        width="95"
      />
      <el-table-column
        align="center"
        prop="appliedVersion"
        label="已应用版本"
        width="105"
      />
      <el-table-column
        align="center"
        label="同步状态"
        width="115"
      >
        <template slot-scope="scope">
          <el-tag
            size="small"
            :type="syncStates[scope.row.syncStatus]?.type || 'info'"
          >
            {{ syncStates[scope.row.syncStatus]?.label || '待同步' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        align="center"
        label="最近生效时间"
        width="175"
      >
        <template slot-scope="scope">{{ parseTime(scope.row.appliedTime) || '—' }}</template>
      </el-table-column>
      <el-table-column
        align="center"
        prop="syncError"
        label="同步错误"
        min-width="240"
        show-overflow-tooltip
      />
      <el-table-column
        align="center"
        label="操作"
        width="100"
      >
        <template slot-scope="scope">
          <el-button
            size="mini"
            v-if="scope.row.syncStatus !== 'applied'"
            v-hasPermi="['monitor:job:edit']"
            type="text"
            :loading="retryingId === scope.row.jobId"
            :disabled="retryingId !== null && retryingId !== scope.row.jobId"
            @click="retrySync(scope.row)"
            >重试同步</el-button
          >
        </template>
      </el-table-column>
    </el-table>
    <pagination
      v-show="total > 0"
      :total="total"
      :page.sync="pageNum"
      :limit.sync="pageSize"
      @pagination="loadRecords()"
    />
    <div
      slot="footer"
      class="dialog-footer"
    >
      <el-button @click="dialogVisible = false">关 闭</el-button>
    </div>
  </el-dialog>
</template>

<script>
import { listJobExecutions, listJobSync, retryJobSync } from '@/api/monitor/job'
import { executionStates, syncStates, notifyJobMutation } from '@/utils/job'
export default {
  name: 'JobRuntime',
  props: {
    visible: Boolean,
    initialTab: {
      type: String,
      default: 'executions',
    },
    jobId: {
      type: [Number, String],
      default: undefined,
    },
    executionId: {
      type: String,
      default: undefined,
    },
  },
  data() {
    return {
      activeTab: 'executions',
      queryJobId: undefined,
      focusedExecutionId: undefined,
      rows: [],
      total: 0,
      pageNum: 1,
      pageSize: 10,
      loading: false,
      loadError: '',
      retryingId: null,
      executionStates: executionStates,
      syncStates: syncStates,
    }
  },
  computed: {
    dialogVisible: {
      get() {
        return this.visible
      },
      set(value) {
        return this.$emit('update:visible', value)
      },
    },
    processingCount() {
      return this.rows.filter((row) =>
        this.activeTab === 'executions'
          ? ['pending', 'submitted', 'running'].includes(row.status)
          : row.syncStatus === 'pending'
      ).length
    },
    runtimeQuery() {
      return [this.visible, this.initialTab, this.jobId, this.executionId]
    },
  },
  watch: {
    runtimeQuery: {
      handler() {
        this.stopRequests()
        if (!this.visible) return
        this.activeTab = this.initialTab
        this.queryJobId = this.jobId == null ? undefined : Number(this.jobId)
        this.focusedExecutionId = this.executionId
        this.loadError = ''
        this.resetPage()
      },
      immediate: true,
    },
  },
  beforeCreate() {
    this._timer = undefined
    this._controller = undefined
    this._requestVersion = 0
  },
  mounted() {
    document.addEventListener('visibilitychange', this.handleVisibility)
  },
  deactivated() {
    this.stopRequests()
    this.$emit('update:visible', false)
  },
  beforeDestroy() {
    this.stopRequests()
    document.removeEventListener('visibilitychange', this.handleVisibility)
  },
  methods: {
    /** 停止自动刷新并取消未完成的请求 */
    stopRequests() {
      clearTimeout(this._timer)
      this._controller?.abort()
      this._requestVersion++
      this.loading = false
    },
    /** 根据执行和同步状态安排下一次刷新 */
    scheduleRefresh() {
      clearTimeout(this._timer)
      const needsRefresh =
        this.processingCount > 0 ||
        this.loadError ||
        (this.activeTab === 'sync' && this.rows.some((row) => row.syncStatus === 'failed'))
      if (this.visible && !document.hidden && needsRefresh) {
        this._timer = setTimeout(() => this.loadRecords(true), 3000)
      }
    },
    /** 查询任务运行记录 */
    async loadRecords(silent = false) {
      if (!this.visible) return
      clearTimeout(this._timer)
      this._controller?.abort()
      this._controller = new AbortController()
      const version = ++this._requestVersion
      if (!silent) this.loading = true
      const query = {
        jobId: this.queryJobId || undefined,
        pageNum: this.pageNum,
        pageSize: this.pageSize,
      }
      if (this.activeTab === 'executions' && this.focusedExecutionId)
        query.executionId = this.focusedExecutionId
      const fetchRecords = this.activeTab === 'executions' ? listJobExecutions : listJobSync
      try {
        const response = await fetchRecords(query, {
          signal: this._controller.signal,
          skipErrorMessage: true,
        })
        if (version !== this._requestVersion || !this.visible) return
        this.rows = response.rows
        this.total = response.total
        this.loadError = ''
      } catch (error) {
        if (version === this._requestVersion && error.code !== 'ERR_CANCELED') {
          this.loadError = '获取记录失败，请刷新重试。'
        }
      } finally {
        if (version === this._requestVersion) {
          this.loading = false
          this.scheduleRefresh()
        }
      }
    },
    /** 重置分页并重新查询 */
    resetPage() {
      this.pageNum = 1
      this.rows = []
      this.total = 0
      this.loadRecords()
    },
    /** 查看当前任务的全部执行记录 */
    showAllExecutions() {
      this.focusedExecutionId = undefined
      this.resetPage()
    },
    /** 重试任务调度同步 */
    async retrySync(row) {
      this.retryingId = row.jobId
      try {
        const response = await retryJobSync(row.jobId)
        notifyJobMutation(this.$modal, response)
        this.$emit('sync-updated')
        await this.loadRecords(true)
      } catch {
        // 请求层已显示重试失败原因，保留当前记录。
      } finally {
        this.retryingId = null
      }
    },
    /** 处理页面显示状态变化 */
    handleVisibility() {
      if (document.hidden) this.stopRequests()
      else if (this.visible) this.loadRecords(true)
    },
  },
}
</script>

<style scoped>
.runtime-status {
  margin: 0 0 12px;
  color: #909399;
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
