<template>
  <el-dialog :title="type === 'log' ? '调度日志详细' : '任务详细'" v-model="dialogVisible" width="780px" style="max-width: calc(100vw - 32px)" append-to-body>
    <div class="detail-wrap">
      <template v-if="type === 'log'">
        <!-- 基本信息 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><InfoFilled /></el-icon> 基本信息
          </div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">日志编号</span><span class="detail-value">{{ form.jobLogId }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">执行状态</span>
                <el-tag v-if="form.status == 0" type="success" size="small">正常</el-tag>
                <el-tag v-else type="danger" size="small">失败</el-tag>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">计划时间</span><span class="detail-value">{{ parseTime(form.scheduledTime) || '-' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务时区</span><span class="detail-value">{{ form.timeZone || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">开始时间</span><span class="detail-value">{{ parseTime(form.startTime) || '-' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">结束时间</span><span class="detail-value">{{ parseTime(form.endTime) || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">记录时间</span><span class="detail-value">{{ parseTime(form.createTime) || '-' }}</span></div>
            </el-col>
            <el-col :span="12" v-if="form.runDurationMs !== null && form.runDurationMs !== undefined">
              <div class="detail-item"><span class="detail-label">执行耗时</span><span class="detail-value">{{ form.runDurationMs }} 毫秒</span></div>
            </el-col>
          </el-row>
        </div>
        <!-- 任务信息 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Clock /></el-icon> 任务信息
          </div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务编号</span><span class="detail-value">{{ form.jobId ?? '历史未关联' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">调度存储</span><span class="detail-value">{{ selectDictLabel(sys_job_store, form.jobStore) || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">执行编号</span><span class="detail-value mono">{{ form.executionId || '历史未关联' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务名称</span><span class="detail-value">{{ form.jobName }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务分组</span>
                <span class="detail-value">{{ form.jobGroup }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务执行器</span>
                <dict-tag :options="sys_job_executor" :value="form.jobExecutor" />
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务触发器</span><span class="detail-value">{{ form.jobTrigger || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">日志信息</span><span class="detail-value">{{ form.jobMessage }}</span></div>
            </el-col>
          </el-row>
        </div>
        <!-- 调用目标 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Operation /></el-icon> 调用目标
          </div>
          <div class="code-body">
            <div class="code-wrap"><pre class="code-pre">{{ form.invokeTarget || '（无）' }}</pre></div>
          </div>
        </div>
        <!-- 调用参数 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Document /></el-icon> 调用参数
          </div>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">位置参数</span><span class="detail-value mono">{{ form.jobArgs || '（无）' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">关键字参数</span><span class="detail-value mono">{{ form.jobKwargs || '（无）' }}</span></div>
            </el-col>
          </el-row>
        </div>
        <!-- 异常信息 -->
        <div class="detail-card" v-if="form.status == 1">
          <div class="detail-card-title error-title">
            <el-icon><Warning /></el-icon> 异常信息
          </div>
          <div class="error-body"><div class="error-msg">{{ form.exceptionInfo }}</div></div>
        </div>
      </template>

      <template v-else>
        <!-- 任务配置 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Setting /></el-icon> 任务配置
          </div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务编号</span><span class="detail-value">{{ form.jobId }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">任务名称</span><span class="detail-value">{{ form.jobName }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">任务分组</span>
                <span class="detail-value">{{ form.jobGroup }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">执行状态</span>
                <el-tag v-if="form.status == 0" type="success" size="small">正常</el-tag>
                <el-tag v-else type="info" size="small">暂停</el-tag>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item">
                <span class="detail-label">任务执行器</span>
                <dict-tag :options="sys_job_executor" :value="form.jobExecutor" />
              </div>
            </el-col>
          </el-row>
        </div>
        <!-- 调度信息 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Calendar /></el-icon> 调度信息
          </div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">调度同步</span>
                <el-tag :type="syncStates[form.syncStatus]?.type || 'warning'" size="small">
                  {{ syncStates[form.syncStatus]?.label || '待同步' }}
                </el-tag>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">配置版本</span><span class="detail-value">
                已应用 {{ form.appliedVersion ?? 0 }} / 最新 {{ form.configVersion ?? '—' }}
              </span></div>
            </el-col>
          </el-row>
          <el-alert v-if="form.syncError" :title="form.syncError" type="error" show-icon :closable="false" />
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">cron 表达式</span><span class="detail-value mono">{{ form.cronExpression }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">Cron 时区</span><span class="detail-value">{{ form.timeZone }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">实际下次调度</span><span class="detail-value">{{ form.status === '1' ? '已停用' : parseTime(form.nextRunTime) || '暂无有效调度观测' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">Cron理论预览</span><span class="detail-value">{{ parseTime(form.cronNextTime) || '无未来时刻' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">调度观测时间</span><span class="detail-value">{{ parseTime(form.scheduleObservedTime) || '-' }}；理论预览仅按Cron规则计算，不代表已安排执行。</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">允许延迟</span>
                <span class="detail-value">{{ form.misfireGraceTime === null ? '不限' : `${form.misfireGraceTime} 秒，超时跳过` }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">最大并发数</span>
                <span class="detail-value">{{ form.maxInstances }}（定时与手动共用）</span>
              </div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">积压处理</span><span class="detail-value">{{ form.coalesce ? '只执行最近一次' : '逐次执行' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">调度存储</span><span class="detail-value">{{ selectDictLabel(sys_job_store, form.jobStore) || '-' }}</span></div>
            </el-col>
          </el-row>
        </div>
        <!-- 执行方法 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Operation /></el-icon> 执行方法
          </div>
          <div class="code-body">
            <div class="code-wrap"><pre class="code-pre">{{ form.invokeTarget || '（无）' }}</pre></div>
          </div>
        </div>
        <!-- 调用参数 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Document /></el-icon> 调用参数
          </div>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">位置参数</span><span class="detail-value mono">{{ form.jobArgs || '（无）' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">关键字参数</span><span class="detail-value mono">{{ form.jobKwargs || '（无）' }}</span></div>
            </el-col>
          </el-row>
        </div>
        <!-- 元信息 -->
        <div class="detail-card">
          <div class="detail-card-title">
            <el-icon><Document /></el-icon> 元信息
          </div>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">创建人</span><span class="detail-value">{{ form.createBy || '-' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">创建时间</span><span class="detail-value">{{ parseTime(form.createTime) || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row">
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">更新人</span><span class="detail-value">{{ form.updateBy || '-' }}</span></div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item"><span class="detail-label">更新时间</span><span class="detail-value">{{ parseTime(form.updateTime) || '-' }}</span></div>
            </el-col>
          </el-row>
          <el-row class="detail-row" v-if="form.remark">
            <el-col :span="24">
              <div class="detail-item"><span class="detail-label">备注</span><span class="detail-value">{{ form.remark }}</span></div>
            </el-col>
          </el-row>
        </div>
      </template>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">关 闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup name="JobDetail">
import { syncStates } from './runtimeState'

const props = defineProps({
  visible: { type: Boolean, default: false },
  row: { type: Object, default: () => ({}) },
  // 'job' 任务详细 | 'log' 调度日志详细
  type: { type: String, default: 'job' }
})

const emit = defineEmits(['update:visible'])

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const { proxy } = getCurrentInstance()
const { sys_job_executor, sys_job_store } = proxy.useDict('sys_job_executor', 'sys_job_store')

const form = computed(() => props.row || {})

</script>

<style scoped>
.detail-label {
  width: 110px;
  flex-shrink: 0;
}
</style>
