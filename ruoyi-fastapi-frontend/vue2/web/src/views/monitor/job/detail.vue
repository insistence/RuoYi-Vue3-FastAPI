<template>
  <el-dialog
    :title="type === 'log' ? '调度日志详细' : '任务详细'"
    :visible.sync="dialogVisible"
    width="780px"
    append-to-body
  >
    <div class="detail-wrap">
      <template v-if="type === 'log'">
        <!-- 基本信息 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-info"></i> 基本信息</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">日志编号</span>
                <span class="detail-value">{{ form.jobLogId }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">执行状态</span>
                <el-tag
                  v-if="form.status == 0"
                  type="success"
                  size="small"
                  >正常</el-tag
                >
                <el-tag
                  v-else
                  type="danger"
                  size="small"
                  >失败</el-tag
                >
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">开始时间</span>
                <span class="detail-value">{{ formatTime(form.startTime) }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">结束时间</span>
                <span class="detail-value">{{ formatTime(form.endTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">记录时间</span>
                <span class="detail-value">{{ formatTime(form.createTime) }}</span>
              </div>
            </el-col>
            <el-col
              v-if="form.runDurationMs != null"
              :span="12"
            >
              <div class="detail-item">
                <span class="detail-label">执行耗时</span>
                <span class="detail-value">{{ form.runDurationMs }} 毫秒</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务编号</span>
                <span class="detail-value">{{ form.jobId || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">计划时间</span>
                <span class="detail-value">{{ formatTime(form.scheduledTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item">
                <span class="detail-label">执行编号</span>
                <span class="detail-value">{{ form.executionId || '-' }}</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 任务信息 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-time"></i> 任务信息</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务名称</span>
                <span class="detail-value">{{ form.jobName }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务分组</span>
                <span class="detail-value">{{ form.jobGroup || '-' }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务执行器</span>
                <dict-tag
                  :options="dict.type.sys_job_executor"
                  :value="form.jobExecutor"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务触发器</span>
                <span class="detail-value">{{ form.jobTrigger || '-' }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">调度存储</span>
                <dict-tag
                  :options="dict.type.sys_job_store"
                  :value="form.jobStore"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">cron时区</span>
                <span class="detail-value">{{ form.timeZone || '-' }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item">
                <span class="detail-label">日志信息</span>
                <span class="detail-value">{{ form.jobMessage }}</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 调用信息 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-s-operation"></i> 调用信息</div>
          <div class="code-body">
            <div class="code-field">
              <div class="code-field-label">调用目标</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ form.invokeTarget || '（无）' }}</pre>
              </div>
            </div>
            <div class="code-field">
              <div class="code-field-label">位置参数</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ formatParameter(form.jobArgs) }}</pre>
              </div>
            </div>
            <div class="code-field">
              <div class="code-field-label">关键字参数</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ formatParameter(form.jobKwargs) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 异常信息 -->
        <div
          v-if="form.status == 1"
          class="detail-card"
        >
          <div class="detail-card-title error-title"><i class="el-icon-warning"></i> 异常信息</div>
          <div class="error-body">
            <div class="error-msg">{{ form.exceptionInfo }}</div>
          </div>
        </div>
      </template>

      <template v-else>
        <!-- 任务配置 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-setting"></i> 任务配置</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务编号</span>
                <span class="detail-value">{{ form.jobId }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务名称</span>
                <span class="detail-value">{{ form.jobName }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务分组</span>
                <span class="detail-value">{{ form.jobGroup || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">执行状态</span>
                <el-tag
                  v-if="form.status == 0"
                  type="success"
                  size="small"
                  >正常</el-tag
                >
                <el-tag
                  v-else
                  type="info"
                  size="small"
                  >暂停</el-tag
                >
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务执行器</span>
                <dict-tag
                  :options="dict.type.sys_job_executor"
                  :value="form.jobExecutor"
                />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">调度存储</span>
                <dict-tag
                  :options="dict.type.sys_job_store"
                  :value="form.jobStore"
                />
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 调度信息 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-date"></i> 调度信息</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">cron 表达式</span>
                <span class="detail-value">{{ form.cronExpression }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">cron时区</span>
                <span class="detail-value">{{ form.timeZone || '-' }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">预期执行时间</span>
                <span class="detail-value">{{ formatTime(form.cronNextTime) }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">调度下次时间</span>
                <span class="detail-value">{{ formatTime(form.nextRunTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">调度观测时间</span>
                <span class="detail-value">{{ formatTime(form.scheduleObservedTime) }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">允许延迟</span>
                <span class="detail-value">{{
                  form.misfireGraceTime === null ? '不限延迟' : form.misfireGraceTime + ' 秒'
                }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">积压处理</span>
                <span class="detail-value">{{ form.coalesce ? '仅最近一次' : '逐次执行' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">最大并发数</span>
                <span class="detail-value">{{ form.maxInstances }}</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 调度同步状态 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-refresh"></i> 同步状态</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">同步状态</span>
                <el-tag
                  size="small"
                  :type="syncState.type"
                  >{{ syncState.label }}</el-tag
                >
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">最近生效时间</span>
                <span class="detail-value">{{ formatTime(form.appliedTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">配置版本</span>
                <span class="detail-value">{{
                  form.configVersion == null ? '-' : form.configVersion
                }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">已应用版本</span>
                <span class="detail-value">{{
                  form.appliedVersion == null ? '-' : form.appliedVersion
                }}</span>
              </div>
            </el-col>
          </el-row>
          <div
            v-if="form.syncError"
            class="error-body"
          >
            <div class="error-msg">{{ form.syncError }}</div>
          </div>
        </div>

        <!-- 执行方法 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-s-operation"></i> 执行方法</div>
          <div class="code-body">
            <div class="code-field">
              <div class="code-field-label">调用目标</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ form.invokeTarget || '（无）' }}</pre>
              </div>
            </div>
            <div class="code-field">
              <div class="code-field-label">位置参数</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ formatParameter(form.jobArgs) }}</pre>
              </div>
            </div>
            <div class="code-field">
              <div class="code-field-label">关键字参数</div>
              <div class="code-wrap">
                <pre class="code-pre">{{ formatParameter(form.jobKwargs) }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 元信息 -->
        <div class="detail-card">
          <div class="detail-card-title"><i class="el-icon-document"></i> 元信息</div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">创建人</span>
                <span class="detail-value">{{ form.createBy || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">创建时间</span>
                <span class="detail-value">{{ formatTime(form.createTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">更新人</span>
                <span class="detail-value">{{ form.updateBy || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">更新时间</span>
                <span class="detail-value">{{ formatTime(form.updateTime) }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row
            v-if="form.remark"
            class="detail-row"
          >
            <el-col :span="24">
              <div class="detail-item">
                <span class="detail-label">备注</span>
                <span class="detail-value">{{ form.remark }}</span>
              </div>
            </el-col>
          </el-row>
        </div>
      </template>
    </div>
  </el-dialog>
</template>

<script>
import { syncStates } from '@/utils/job'

export default {
  name: 'JobDetail',
  dicts: ['sys_job_store', 'sys_job_executor'],
  props: {
    visible: { type: Boolean, default: false },
    row: { type: Object, default: () => ({}) },
    // 'job' 任务详细 | 'log' 调度日志详细
    type: { type: String, default: 'job' },
  },
  computed: {
    form() {
      return this.row || {}
    },
    dialogVisible: {
      get() {
        return this.visible
      },
      set(value) {
        this.$emit('update:visible', value)
      },
    },
    syncState() {
      return syncStates[this.form.syncStatus] || syncStates.pending
    },
  },
  methods: {
    formatParameter(value) {
      if (value === null || value === undefined || value === '') return '（无）'
      return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
    },
    formatTime(value) {
      return value ? this.parseTime(value) : '-'
    },
  },
}
</script>

<style scoped>
.detail-label {
  width: 80px;
}

.code-field + .code-field {
  margin-top: 12px;
}

.code-field-label {
  margin-bottom: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
