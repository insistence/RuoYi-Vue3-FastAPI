<template>
  <div>
    <el-drawer
      title="文件存储对账"
      :visible.sync="visible"
      size="88%"
      append-to-body
      @closed="handleClosed"
    >
      <div class="drawer-content">
        <el-alert
          title="对账会双向检查文件信息表与公开、受保护、回收站存储区；隔离区不对外提供静态访问。修复操作仅使用异常中已校验的相对路径。"
          type="info"
          :closable="false"
          show-icon
          class="mb12"
        />

        <div class="reconcile-summary">
          <div class="summary-card summary-card--danger">
            <div class="summary-card__label">待处理</div>
            <div class="summary-card__value">{{ stats.openCount }}</div>
            <div class="summary-card__hint">需要确认或修复的异常</div>
          </div>
          <div class="summary-card summary-card--critical">
            <div class="summary-card__label">严重异常</div>
            <div class="summary-card__value">{{ stats.criticalCount }}</div>
            <div class="summary-card__hint">文件缺失、错位或内容不一致</div>
          </div>
          <div class="summary-card summary-card--warning">
            <div class="summary-card__label">警告异常</div>
            <div class="summary-card__value">{{ stats.warningCount }}</div>
            <div class="summary-card__hint">孤立文件或回收状态异常</div>
          </div>
          <div class="summary-card summary-card--quarantine">
            <div class="summary-card__label">隔离文件</div>
            <div class="summary-card__value">{{ stats.quarantinedCount }}</div>
            <div class="summary-card__hint">仅管理员可恢复或永久删除</div>
          </div>
          <div class="summary-card summary-card--run">
            <div class="summary-card__label">最近任务</div>
            <div class="summary-card__status">
              <el-tag :type="runStatusType(latestRun.status)">
                {{ runStatusLabel(latestRun.status) }}
              </el-tag>
            </div>
            <div class="summary-card__hint">
              {{ latestRun.startedTime ? parseTime(latestRun.startedTime) : '尚未执行' }}
            </div>
          </div>
        </div>

        <div class="reconcile-toolbar">
          <div class="reconcile-toolbar__tip">
            完整摘要校验会读取全部文件内容，建议在低峰期启用。
          </div>
          <div class="reconcile-toolbar__actions">
            <span class="mr8">校验 SHA-256</span>
            <el-switch
              v-model="checkHash"
              class="mr12"
            />
            <el-button
              type="primary"
              plain
              size="mini"
              icon="el-icon-refresh"
              :loading="scanning"
              :disabled="latestRun.status === 'running'"
              @click="handleStart"
              >开始对账</el-button
            >
          </div>
        </div>

        <el-tabs
          v-model="activeTab"
          @tab-click="handleTabClick"
        >
          <el-tab-pane
            label="异常明细"
            name="issues"
          >
            <el-form
              ref="issueQueryForm"
              :model="issueQuery"
              :inline="true"
              label-width="68px"
            >
              <el-form-item
                label="关键字"
                prop="keyword"
              >
                <el-input
                  v-model="issueQuery.keyword"
                  placeholder="文件名、ID或相对路径"
                  clearable
                  size="small"
                  style="width: 200px"
                  @keyup.enter.native="handleIssueQuery"
                />
              </el-form-item>
              <el-form-item
                label="异常类型"
                prop="issueType"
              >
                <el-select
                  v-model="issueQuery.issueType"
                  placeholder="全部类型"
                  clearable
                  size="small"
                  style="width: 200px"
                >
                  <el-option
                    v-for="item in issueTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item
                label="严重级别"
                prop="severity"
              >
                <el-select
                  v-model="issueQuery.severity"
                  placeholder="全部级别"
                  clearable
                  size="small"
                  style="width: 200px"
                >
                  <el-option
                    label="严重"
                    value="critical"
                  />
                  <el-option
                    label="警告"
                    value="warning"
                  />
                  <el-option
                    label="提示"
                    value="info"
                  />
                </el-select>
              </el-form-item>
              <el-form-item
                label="处理状态"
                prop="status"
              >
                <el-select
                  v-model="issueQuery.status"
                  placeholder="全部状态"
                  clearable
                  size="small"
                  style="width: 200px"
                >
                  <el-option
                    label="待处理"
                    value="open"
                  />
                  <el-option
                    label="已忽略"
                    value="ignored"
                  />
                  <el-option
                    label="已隔离"
                    value="quarantined"
                  />
                  <el-option
                    label="已解决"
                    value="resolved"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label-width="0">
                <el-button
                  type="primary"
                  size="mini"
                  icon="el-icon-search"
                  @click="handleIssueQuery"
                  >搜索</el-button
                >
                <el-button
                  size="mini"
                  icon="el-icon-refresh"
                  @click="resetIssueQuery"
                  >重置</el-button
                >
              </el-form-item>
            </el-form>

            <el-table
              v-loading="issueLoading"
              :data="issueList"
            >
              <el-table-column
                label="级别"
                align="center"
                width="80"
              >
                <template slot-scope="scope">
                  <el-tag :type="severityTagType(scope.row.severity)">
                    {{ severityLabel(scope.row.severity) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                label="异常类型"
                align="center"
                width="130"
              >
                <template slot-scope="scope">
                  {{ issueTypeLabel(scope.row.issueType) }}
                </template>
              </el-table-column>
              <el-table-column
                label="文件"
                align="left"
                prop="originalName"
                min-width="170"
                show-overflow-tooltip
              >
                <template slot-scope="scope">
                  <div>{{ scope.row.originalName || '未登记文件' }}</div>
                  <div class="cell-secondary">
                    {{ scope.row.fileId || '-' }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                label="存储位置"
                align="left"
                min-width="230"
              >
                <template slot-scope="scope">
                  <div :title="formatLocation(scope.row.expectedRoot, scope.row.expectedKey)">
                    预期：{{ formatLocation(scope.row.expectedRoot, scope.row.expectedKey) }}
                  </div>
                  <div
                    class="cell-secondary"
                    :title="formatLocation(scope.row.actualRoot, scope.row.actualKey)"
                  >
                    实际：{{ formatLocation(scope.row.actualRoot, scope.row.actualKey) }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                label="大小"
                align="right"
                width="130"
              >
                <template slot-scope="scope">
                  <div>预期：{{ formatOptionalSize(scope.row.expectedSize) }}</div>
                  <div class="cell-secondary">
                    实际：{{ formatOptionalSize(scope.row.actualSize) }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                label="状态"
                align="center"
                width="90"
              >
                <template slot-scope="scope">
                  <el-tag :type="issueStatusType(scope.row.status)">
                    {{ issueStatusLabel(scope.row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                label="异常说明"
                align="left"
                prop="detail"
                min-width="180"
                show-overflow-tooltip
              />
              <el-table-column
                label="最近发现"
                align="center"
                width="170"
              >
                <template slot-scope="scope">
                  {{ parseTime(scope.row.lastSeenTime) }}
                </template>
              </el-table-column>
              <el-table-column
                label="操作"
                align="center"
                width="70"
                fixed="right"
              >
                <template slot-scope="scope">
                  <el-tooltip
                    v-if="scope.row.availableActions && scope.row.availableActions.length"
                    :content="
                      latestRun.status === 'running' ? '对账任务运行中，请等待扫描完成' : '处理异常'
                    "
                    placement="top"
                  >
                    <span class="reconcile-action-trigger">
                      <el-dropdown
                        trigger="click"
                        :disabled="latestRun.status === 'running'"
                        @command="handleCommand($event, scope.row)"
                      >
                        <el-button
                          type="text"
                          icon="el-icon-setting"
                          class="table-operation-button"
                          :disabled="latestRun.status === 'running'"
                        />
                        <el-dropdown-menu slot="dropdown">
                          <el-dropdown-item
                            v-for="action in scope.row.availableActions"
                            :key="action"
                            :command="action"
                          >
                            {{ actionLabel(action) }}
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </el-dropdown>
                    </span>
                  </el-tooltip>
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
            <pagination
              v-show="issueTotal > 0"
              :total="issueTotal"
              :page.sync="issueQuery.pageNum"
              :limit.sync="issueQuery.pageSize"
              @pagination="getIssueList"
            />
          </el-tab-pane>

          <el-tab-pane
            label="任务记录"
            name="runs"
          >
            <el-table
              v-loading="runLoading"
              :data="runList"
            >
              <el-table-column
                label="任务状态"
                align="center"
                width="100"
              >
                <template slot-scope="scope">
                  <el-tag :type="runStatusType(scope.row.status)">
                    {{ runStatusLabel(scope.row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                label="触发方式"
                align="center"
                width="100"
              >
                <template slot-scope="scope">
                  {{ scope.row.triggerType === 'scheduled' ? '定时任务' : '手动' }}
                </template>
              </el-table-column>
              <el-table-column
                label="摘要校验"
                align="center"
                width="90"
              >
                <template slot-scope="scope">{{ scope.row.checkHash ? '是' : '否' }}</template>
              </el-table-column>
              <el-table-column
                label="文件记录"
                align="right"
                prop="scannedFileCount"
                width="100"
              />
              <el-table-column
                label="物理文件"
                align="right"
                prop="scannedStorageCount"
                width="100"
              />
              <el-table-column
                label="发现异常"
                align="right"
                prop="issueCount"
                width="100"
              />
              <el-table-column
                label="新增异常"
                align="right"
                prop="newIssueCount"
                width="100"
              />
              <el-table-column
                label="自动恢复"
                align="right"
                prop="resolvedIssueCount"
                width="100"
              />
              <el-table-column
                label="发起人"
                align="center"
                prop="startedBy"
                width="110"
                show-overflow-tooltip
              />
              <el-table-column
                label="开始时间"
                align="center"
                width="170"
              >
                <template slot-scope="scope">{{ parseTime(scope.row.startedTime) }}</template>
              </el-table-column>
              <el-table-column
                label="完成时间"
                align="center"
                width="170"
              >
                <template slot-scope="scope">
                  {{ scope.row.finishedTime ? parseTime(scope.row.finishedTime) : '-' }}
                </template>
              </el-table-column>
              <el-table-column
                label="失败原因"
                align="left"
                prop="errorMessage"
                min-width="180"
                show-overflow-tooltip
              />
            </el-table>
            <pagination
              v-show="runTotal > 0"
              :total="runTotal"
              :page.sync="runQuery.pageNum"
              :limit.sync="runQuery.pageSize"
              @pagination="getRunList"
            />
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <el-dialog
      :title="actionLabel(handleForm.action)"
      :visible.sync="handleOpen"
      width="520px"
      append-to-body
    >
      <el-alert
        v-if="actionDescriptions[handleForm.action]"
        :title="actionDescriptions[handleForm.action]"
        :type="dangerousActions.indexOf(handleForm.action) >= 0 ? 'warning' : 'info'"
        :closable="false"
        show-icon
        class="mb16"
      />
      <el-form
        ref="handleForm"
        :model="handleForm"
        :rules="handleRules"
        label-width="90px"
      >
        <el-form-item
          v-if="handleForm.action === 'register_orphan'"
          label="原始文件名"
          prop="originalName"
        >
          <el-input
            v-model="handleForm.originalName"
            placeholder="需与物理文件扩展名一致"
            maxlength="255"
          />
        </el-form-item>
        <el-form-item
          label="处理原因"
          prop="reason"
        >
          <el-input
            v-model="handleForm.reason"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="请填写处理依据，内容会保留在对账记录中"
          />
        </el-form-item>
      </el-form>
      <div
        slot="footer"
        class="dialog-footer"
      >
        <el-button @click="handleOpen = false">取 消</el-button>
        <el-button
          type="primary"
          :loading="handling"
          @click="submitHandle"
        >
          确 定
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
  getFileReconcileStats,
  handleFileReconcileIssue,
  listFileReconcileIssue,
  listFileReconcileRun,
  startFileReconcile,
} from '@/api/system/file'
import { formatFileSize } from './fileFormatters'

export default {
  name: 'FileReconcileDrawer',
  data() {
    const validateOriginalName = (_rule, value, callback) => {
      if (this.handleForm.action === 'register_orphan' && !value) {
        callback(new Error('登记孤立文件时必须填写原始文件名'))
        return
      }
      callback()
    }
    return {
      visible: false,
      activeTab: 'issues',
      issueLoading: false,
      runLoading: false,
      scanning: false,
      handling: false,
      checkHash: false,
      issueList: [],
      runList: [],
      issueTotal: 0,
      runTotal: 0,
      pollTimer: null,
      currentIssueId: null,
      handleOpen: false,
      stats: {
        openCount: 0,
        criticalCount: 0,
        warningCount: 0,
        ignoredCount: 0,
        quarantinedCount: 0,
        latestRun: null,
      },
      issueQuery: {
        pageNum: 1,
        pageSize: 10,
        keyword: undefined,
        issueType: undefined,
        severity: undefined,
        status: 'open',
      },
      runQuery: {
        pageNum: 1,
        pageSize: 10,
      },
      handleForm: {
        action: '',
        reason: '',
        originalName: '',
      },
      handleRules: {
        reason: [{ required: true, message: '处理原因不能为空', trigger: 'blur' }],
        originalName: [{ validator: validateOriginalName, trigger: 'blur' }],
      },
      issueTypeOptions: [
        { label: '元数据不合法', value: 'invalid_metadata' },
        { label: '物理文件缺失', value: 'missing_file' },
        { label: '有效文件位于回收站', value: 'unexpected_trash' },
        { label: '回收文件位于正式区', value: 'unexpected_source' },
        { label: '重复物理文件', value: 'duplicate_file' },
        { label: '存储区域错误', value: 'wrong_storage_root' },
        { label: '文件大小不一致', value: 'size_mismatch' },
        { label: '文件摘要不一致', value: 'hash_mismatch' },
        { label: '孤立物理文件', value: 'orphan_file' },
        { label: '不安全目录项', value: 'unsafe_entry' },
      ],
      dangerousActions: ['delete_quarantine', 'accept_current', 'register_orphan'],
      actionDescriptions: {
        ignore: '保留异常但不再计入待处理数量，后续可重新打开。',
        reopen: '将已忽略异常重新置为待处理。',
        restore_source: '把回收区中的物理文件恢复到登记的正式存储位置。',
        move_to_trash: '把正式存储区中的回收文件移入登记的回收区位置。',
        move_to_expected_root: '把物理文件移动到文件信息表登记的存储区域。',
        quarantine_file: '把异常副本或孤立文件移入不可公开访问的隔离区。',
        restore_quarantine: '把隔离文件恢复到隔离前的位置，异常会重新打开。',
        delete_quarantine: '永久删除隔离文件，此操作不可恢复。',
        accept_current: '以当前物理文件重新计算大小和摘要并更新文件信息表。',
        register_orphan: '把孤立物理文件登记为当前管理员所有的有效文件。',
      },
    }
  },
  computed: {
    latestRun() {
      return this.stats.latestRun || {}
    },
  },
  beforeDestroy() {
    clearInterval(this.pollTimer)
  },
  methods: {
    open() {
      this.visible = true
      this.activeTab = 'issues'
      this.refreshAll()
      this.startPolling()
    },
    refreshAll() {
      this.getStats()
      this.getIssueList()
      this.getRunList()
    },
    getStats() {
      return getFileReconcileStats().then((response) => {
        Object.assign(this.stats, response.data)
      })
    },
    getIssueList() {
      this.issueLoading = true
      return listFileReconcileIssue(this.issueQuery)
        .then((response) => {
          this.issueList = response.rows
          this.issueTotal = response.total
        })
        .finally(() => {
          this.issueLoading = false
        })
    },
    getRunList() {
      this.runLoading = true
      return listFileReconcileRun(this.runQuery)
        .then((response) => {
          this.runList = response.rows
          this.runTotal = response.total
        })
        .finally(() => {
          this.runLoading = false
        })
    },
    handleStart() {
      this.scanning = true
      startFileReconcile({ checkHash: this.checkHash })
        .then(() => {
          this.$modal.msgSuccess('文件存储对账任务已启动')
          this.refreshAll()
        })
        .finally(() => {
          this.scanning = false
        })
    },
    handleIssueQuery() {
      this.issueQuery.pageNum = 1
      this.getIssueList()
    },
    resetIssueQuery() {
      this.$refs.issueQueryForm.resetFields()
      this.issueQuery.pageNum = 1
      this.issueQuery.status = 'open'
      this.getIssueList()
    },
    handleTabClick(tab) {
      if (tab.name === 'runs') this.getRunList()
    },
    handleCommand(action, row) {
      this.currentIssueId = row.issueId
      Object.assign(this.handleForm, {
        action,
        reason: '',
        originalName: row.originalName || (row.actualKey ? row.actualKey.split('/').pop() : ''),
      })
      this.handleOpen = true
      this.$nextTick(() => this.$refs.handleForm.clearValidate())
    },
    submitHandle() {
      this.$refs.handleForm.validate((valid) => {
        if (!valid) return
        this.handling = true
        handleFileReconcileIssue(this.currentIssueId, {
          action: this.handleForm.action,
          reason: this.handleForm.reason,
          originalName:
            this.handleForm.action === 'register_orphan' ? this.handleForm.originalName : undefined,
        })
          .then(() => {
            this.$modal.msgSuccess('文件存储异常处理成功')
            this.handleOpen = false
            this.refreshAll()
            this.$emit('refresh')
          })
          .finally(() => {
            this.handling = false
          })
      })
    },
    startPolling() {
      clearInterval(this.pollTimer)
      this.pollTimer = setInterval(() => {
        if (!this.visible || this.latestRun.status !== 'running') return
        this.refreshAll()
      }, 3000)
    },
    handleClosed() {
      clearInterval(this.pollTimer)
      this.pollTimer = null
      this.handleOpen = false
    },
    formatLocation(root, key) {
      return root && key ? `${root}:${key}` : '-'
    },
    formatOptionalSize(size) {
      return size === null || size === undefined ? '-' : formatFileSize(size)
    },
    issueTypeLabel(type) {
      const option = this.issueTypeOptions.find((item) => item.value === type)
      return option ? option.label : type
    },
    severityLabel(severity) {
      return { critical: '严重', warning: '警告', info: '提示' }[severity] || severity
    },
    severityTagType(severity) {
      return { critical: 'danger', warning: 'warning', info: 'info' }[severity] || 'info'
    },
    issueStatusLabel(status) {
      return (
        {
          open: '待处理',
          ignored: '已忽略',
          quarantined: '已隔离',
          resolved: '已解决',
        }[status] || status
      )
    },
    issueStatusType(status) {
      return (
        {
          open: 'danger',
          ignored: 'info',
          quarantined: 'warning',
          resolved: 'success',
        }[status] || 'info'
      )
    },
    runStatusLabel(status) {
      return (
        {
          running: '运行中',
          completed: '已完成',
          failed: '失败',
        }[status] || '尚未执行'
      )
    },
    runStatusType(status) {
      return (
        {
          running: 'warning',
          completed: 'success',
          failed: 'danger',
        }[status] || 'info'
      )
    },
    actionLabel(action) {
      return (
        {
          ignore: '忽略异常',
          reopen: '重新打开',
          restore_source: '恢复到正式区',
          move_to_trash: '移入回收区',
          move_to_expected_root: '移到预期区域',
          quarantine_file: '隔离文件',
          restore_quarantine: '恢复隔离文件',
          delete_quarantine: '永久删除隔离文件',
          accept_current: '接受当前文件',
          register_orphan: '登记孤立文件',
        }[action] || action
      )
    },
  },
}
</script>

<style scoped>
.drawer-content {
  padding: 0 20px 20px;
}

.reconcile-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  position: relative;
  overflow: hidden;
  min-height: 112px;
  padding: 16px 18px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.summary-card::before {
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  content: '';
  background: var(--card-color);
}

.summary-card--danger {
  --card-color: #f56c6c;
}
.summary-card--critical {
  --card-color: #b42318;
}
.summary-card--warning {
  --card-color: #e6a23c;
}
.summary-card--quarantine {
  --card-color: #7f56d9;
}
.summary-card--run {
  --card-color: #409eff;
}

.summary-card__label {
  color: #909399;
  font-size: 14px;
}

.summary-card__value {
  margin-top: 7px;
  color: #303133;
  font-size: 28px;
  font-weight: 600;
  line-height: 34px;
}

.summary-card__status {
  display: flex;
  align-items: center;
  height: 41px;
}

.summary-card__hint {
  overflow: hidden;
  color: #c0c4cc;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reconcile-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  background: #f5f7fa;
}

.reconcile-toolbar__tip {
  color: #909399;
  font-size: 13px;
}

.reconcile-toolbar__actions {
  display: flex;
  align-items: center;
  white-space: nowrap;
}

.reconcile-action-trigger {
  display: inline-flex;
  align-items: center;
}

.cell-secondary {
  overflow: hidden;
  margin-top: 3px;
  color: #909399;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1400px) {
  .reconcile-summary {
    grid-template-columns: repeat(3, minmax(160px, 1fr));
  }
}
</style>
