<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
         <el-form-item label="任务名称" prop="jobName">
            <el-input
               v-model="queryParams.jobName"
               placeholder="请输入任务名称"
               clearable
               style="width: 200px"
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="业务分组" prop="jobGroup">
            <el-input v-model="queryParams.jobGroup" placeholder="请输入业务分组" clearable style="width: 200px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="任务状态" prop="status">
            <el-select v-model="queryParams.status" placeholder="请选择任务状态" clearable style="width: 200px">
               <el-option
                  v-for="dict in sys_job_status"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
               />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button
               type="primary"
               plain
               icon="Plus"
               @click="handleAdd"
               v-hasPermi="['monitor:job:add']"
            >新增</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="success"
               plain
               icon="Edit"
               :disabled="single"
               @click="handleUpdate"
               v-hasPermi="['monitor:job:edit']"
            >修改</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="danger"
               plain
               icon="Delete"
               :disabled="multiple"
               @click="handleDelete"
               v-hasPermi="['monitor:job:remove']"
            >删除</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="warning"
               plain
               icon="Download"
               @click="handleExport"
               v-hasPermi="['monitor:job:export']"
            >导出</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button
               type="info"
               plain
               icon="Operation"
               @click="handleJobLog"
               v-hasPermi="['monitor:job:query']"
            >日志</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button type="info" plain icon="Tickets" @click="handleRuntime('executions')"
               v-hasPermi="['monitor:job:query']">运行记录</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="jobList" @selection-change="handleSelectionChange">
         <el-table-column type="selection" width="55" align="center" />
         <el-table-column label="任务编号" width="100" align="center" prop="jobId" />
         <el-table-column label="任务名称" align="center" :show-overflow-tooltip="true">
            <template #default="scope">
               <a class="link-type" style="cursor:pointer" @click="handleView(scope.row)">{{ scope.row.jobName }}</a>
            </template>
         </el-table-column>
         <el-table-column label="业务分组" align="center" prop="jobGroup">
            <template #default="scope">
               {{ scope.row.jobGroup }}
            </template>
         </el-table-column>
         <el-table-column label="调用目标字符串" align="center" prop="invokeTarget" :show-overflow-tooltip="true" />
         <el-table-column label="cron执行表达式" align="center" prop="cronExpression" :show-overflow-tooltip="true" />
         <el-table-column label="cron时区" align="center" prop="timeZone" width="150" />
         <el-table-column label="调度同步" align="center" width="115">
            <template #default="scope">
               <el-button v-if="canQueryRuntime" link :type="syncStates[scope.row.syncStatus]?.type || 'warning'"
                  @click="handleRuntime('sync', scope.row)">
                  {{ syncStates[scope.row.syncStatus]?.label || '待同步' }}
               </el-button>
               <span v-else>{{ syncStates[scope.row.syncStatus]?.label || '待同步' }}</span>
            </template>
         </el-table-column>
         <el-table-column label="状态" align="center">
            <template #default="scope">
               <el-switch
                  v-model="scope.row.status"
                  active-value="0"
                  inactive-value="1"
                  :disabled="changingIds.has(scope.row.jobId)"
                  :aria-label="`任务 ${scope.row.jobName} 的启停状态`"
                  @change="handleStatusChange(scope.row)"
               ></el-switch>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="200" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-tooltip content="修改" placement="top">
                  <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['monitor:job:edit']"></el-button>
               </el-tooltip>
               <el-tooltip content="删除" placement="top">
                  <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['monitor:job:remove']"></el-button>
               </el-tooltip>
               <el-tooltip content="执行一次" placement="top">
                  <el-button link type="primary" icon="CaretRight" :loading="runningIds.has(scope.row.jobId)"
                     :aria-label="`立即执行 ${scope.row.jobName}`" @click="handleRun(scope.row)"
                     v-hasPermi="['monitor:job:changeStatus']"></el-button>
               </el-tooltip>
               <el-tooltip content="调度日志" placement="top">
                  <el-button link type="primary" icon="Operation" @click="handleJobLog(scope.row)" v-hasPermi="['monitor:job:query']"></el-button>
               </el-tooltip>
            </template>
         </el-table-column>
      </el-table>

      <pagination
         v-show="total > 0"
         :total="total"
         v-model:page="queryParams.pageNum"
         v-model:limit="queryParams.pageSize"
         @pagination="getList"
      />

      <!-- 添加或修改定时任务对话框 -->
      <el-dialog :title="title" v-model="open" width="820px" class="scrollbar" style="max-width: calc(100vw - 32px)" append-to-body
         :close-on-click-modal="!submitting" :close-on-press-escape="!submitting" :show-close="!submitting" destroy-on-close>
         <el-form ref="jobRef" :model="form" :rules="rules" label-width="120px">
            <el-row>
               <el-col :span="24">
                  <el-form-item label="任务名称" prop="jobName">
                     <el-input v-model="form.jobName" maxlength="64" placeholder="同一业务分组内名称唯一" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item label="业务分组" prop="jobGroup">
                     <el-input v-model="form.jobGroup" maxlength="64" placeholder="例如 default、报表、文件维护" />
                  </el-form-item>
               </el-col>
               <el-col :span="12">
                  <el-form-item prop="jobExecutor">
                     <template #label>
                        <span>
                           任务执行器
                           <el-tooltip placement="top">
                              <template #content>
                                 <div>
                                    调用方法为异步函数时此选项无效
                                 </div>
                              </template>
                              <el-icon><question-filled /></el-icon>
                           </el-tooltip>
                        </span>
                     </template>
                     <el-select v-model="form.jobExecutor" placeholder="请选择任务执行器">
                        <el-option
                           v-for="dict in sys_job_executor"
                           :key="dict.value"
                           :label="dict.label"
                           :value="dict.value"
                        ></el-option>
                     </el-select>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="调度存储" prop="jobStore">
                     <el-select v-model="form.jobStore" placeholder="请选择调度存储">
                        <el-option v-for="dict in sys_job_store" :key="dict.value" :label="dict.label" :value="dict.value" />
                     </el-select>
                     <div class="form-help">内存存储重启后重建计划；数据库和Redis可保留下次调度进度。</div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item prop="invokeTarget">
                     <template #label>
                        <span>
                           调用方法
                           <el-tooltip placement="top">
                              <template #content>
                                 <div>
                                    调用示例：module_task.scheduler_test.job
                                 </div>
                              </template>
                              <el-icon><question-filled /></el-icon>
                           </el-tooltip>
                        </span>
                     </template>
                     <el-input v-model="form.invokeTarget" placeholder="请输入调用目标字符串" />
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="位置参数" prop="jobArgs">
                     <json-editor v-model="form.jobArgs" label="位置参数" value-type="array" :validate="value => parseJobParameter(value, 'jobArgs')" />
                     <div class="form-help">无参数填写 []，数组内可使用字符串、数字、布尔值和对象。</div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="关键字参数" prop="jobKwargs">
                     <json-editor v-model="form.jobKwargs" label="关键字参数" value-type="object" :validate="value => parseJobParameter(value, 'jobKwargs')" />
                     <div class="form-help">无参数填写 {}，属性名需与函数参数名一致。</div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="cron表达式" prop="cronExpression">
                     <el-input v-model="form.cronExpression" placeholder="请输入cron执行表达式">
                        <template #append>
                           <el-button type="primary" @click="handleShowCron">
                              生成表达式
                              <i class="el-icon-time el-icon--right"></i>
                           </el-button>
                        </template>
                     </el-input>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="cron时区" prop="timeZone">
                     <el-select v-model="form.timeZone" filterable allow-create placeholder="选择IANA时区">
                        <el-option v-for="zone in timeZoneOptions" :key="zone" :label="zone" :value="zone" />
                     </el-select>
                  </el-form-item>
               </el-col>
               <el-col :span="24" v-if="form.jobId !== undefined">
                  <el-form-item label="状态">
                     <el-radio-group v-model="form.status">
                        <el-radio
                           v-for="dict in sys_job_status"
                           :key="dict.value"
                           :value="dict.value"
                        >{{ dict.label }}</el-radio>
                     </el-radio-group>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="允许延迟" prop="misfireGraceTime">
                     <el-input-number v-if="!unlimitedDelay" v-model="form.misfireGraceTime" :min="1" :max="2147483647" :precision="0" controls-position="right" aria-label="允许延迟秒数" />
                     <span v-if="!unlimitedDelay" class="field-unit">秒</span>
                     <el-switch v-model="unlimitedDelay" active-text="不限延迟" aria-label="是否不限延迟" />
                     <div class="form-help">从计划时刻起计算，超过宽限时间则跳过本次定时执行；不限延迟时允许补跑过期计划。</div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="积压处理" prop="coalesce">
                     <el-radio-group v-model="form.coalesce">
                        <el-radio-button :value="false">逐次执行</el-radio-button>
                        <el-radio-button :value="true">只执行最近一次</el-radio-button>
                     </el-radio-group>
                     <div class="form-help">同次检查发现多个到期计划时采用此规则，仍受允许延迟限制。</div>
                  </el-form-item>
               </el-col>
               <el-col :span="24">
                  <el-form-item label="最大并发数" prop="maxInstances">
                     <el-input-number v-model="form.maxInstances" :min="1" :max="2147483647" :precision="0" controls-position="right" />
                     <div class="form-help">定时与手动执行共同遵守此上限；超限时跳过并记录原因，不排队等待。</div>
                  </el-form-item>
               </el-col>
            </el-row>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" :loading="submitting" @click="submitForm">确 定</el-button>
               <el-button :disabled="submitting" @click="cancel">取 消</el-button>
            </div>
         </template>
      </el-dialog>

     <el-dialog title="Cron表达式生成器" v-model="openCron" append-to-body destroy-on-close>
       <crontab
         ref="crontabRef"
         :expression="expression"
         :time-zone="form.timeZone"
         @hide="openCron=false"
         @fill="crontabFill"
       />
     </el-dialog>

      <!-- 任务详细 -->
      <job-detail v-model:visible="openView" :row="form" type="job" />
      <job-runtime v-model:visible="runtimeOpen" :initial-tab="runtimeContext.tab"
         :job-id="runtimeContext.jobId" :execution-id="runtimeContext.executionId" @sync-updated="getList" />
   </div>
</template>

<script setup name="Job">
import Crontab from '@/components/Crontab'
import JobDetail from './detail'
import JobRuntime from './runtime'
import JsonEditor from '@/components/JsonEditor'
import { syncStates, notifyJobMutation } from './runtimeState'
import { parseJobParameter, buildJobPayload } from './jobForm'
import { checkPermi } from '@/utils/permission'
import { listJob, getJob, delJob, addJob, updateJob, runJob, changeJobStatus } from "@/api/monitor/job"
import useUserStore from '@/store/modules/user'

const router = useRouter();
const userStore = useUserStore();
const { proxy } = getCurrentInstance();
const { sys_job_status, sys_job_executor, sys_job_store } = proxy.useDict("sys_job_status", "sys_job_executor", "sys_job_store");

const jobList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const single = ref(true);
const multiple = ref(true);
const total = ref(0);
const title = ref("");
const openView = ref(false);
const openCron = ref(false);
const expression = ref("");
const submitting = ref(false);
const changingIds = reactive(new Set());
const runningIds = reactive(new Set());
const runtimeOpen = ref(false);
const runtimeContext = ref({ tab: 'executions' });
const canQueryRuntime = computed(() => checkPermi(['monitor:job:query']));
let syncRefreshTimer;
let listController;
let listVersion = 0;
let pageActive = true;
const timeZoneOptions = typeof Intl.supportedValuesOf === 'function'
  ? Intl.supportedValuesOf('timeZone')
  : [userStore.appTimezone];

/** 显示对应参数字段的JSON格式错误 */
function validateParameter(rule, value, callback) {
  try {
    parseJobParameter(value, rule.field);
    callback();
  } catch (error) {
    callback(error);
  }
}

/** 校验允许延迟，空值表示不限延迟 */
function validateGraceTime(_rule, value, callback) {
  const valid = value === null || Number.isInteger(value) && value >= 1 && value <= 2147483647;
  callback(valid ? undefined : new Error("允许延迟必须为正整数秒"));
}

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    jobName: undefined,
    jobGroup: undefined,
    status: undefined
  },
  rules: {
    jobName: [{ required: true, message: "任务名称不能为空", trigger: "blur" }],
    jobGroup: [{ required: true, whitespace: true, message: "业务分组不能为空", trigger: "blur" }],
    jobStore: [{ required: true, message: "调度存储不能为空", trigger: "change" }],
    jobArgs: [{ validator: validateParameter, trigger: "blur" }],
    jobKwargs: [{ validator: validateParameter, trigger: "blur" }],
    maxInstances: [{ required: true, type: "number", min: 1, message: "最大并发数必须为正整数", trigger: "change" }],
    misfireGraceTime: [{ validator: validateGraceTime, trigger: "change" }],
    invokeTarget: [{ required: true, message: "调用目标字符串不能为空", trigger: "blur" }],
    cronExpression: [{ required: true, message: "cron执行表达式不能为空", trigger: "change" }],
    timeZone: [{ required: true, message: "cron时区不能为空", trigger: "blur" }]
  }
});

const { queryParams, form, rules } = toRefs(data);
const unlimitedDelay = computed({
  get: () => form.value.misfireGraceTime === null,
  set: (value) => {
    form.value.misfireGraceTime = value ? null : 1;
  }
});

/** 查询定时任务列表 */
async function getList(options = {}) {
  const silent = options?.silent === true;
  clearTimeout(syncRefreshTimer);
  listController?.abort();
  listController = new AbortController();
  const version = ++listVersion;
  if (!silent) loading.value = true;
  try {
    const response = await listJob({ ...queryParams.value }, { signal: listController.signal, skipErrorMessage: silent });
    if (version !== listVersion) return;
    jobList.value = response.rows;
    total.value = response.total;
  } catch {
    // 保留当前列表；主动请求的失败信息由请求层显示。
  } finally {
    if (version === listVersion) {
      loading.value = false;
      if (pageActive && !document.hidden && jobList.value.some(job => ['pending', 'failed'].includes(job.syncStatus))) {
        syncRefreshTimer = setTimeout(() => getList({ silent: true }), 3000);
      }
    }
  }
}

/** 打开任务运行记录 */
function handleRuntime(tab, row, executionId) {
  if (!canQueryRuntime.value) return;
  runtimeContext.value = { tab, jobId: row?.jobId, executionId };
  runtimeOpen.value = true;
}

/** 显示任务变更结果 */
function showMutationResult(response) {
  notifyJobMutation(proxy.$modal, response);
  if (response.data?.syncStatus === 'failed') {
    const affected = response.data.jobs;
    handleRuntime('sync', affected?.length === 1 ? affected[0] : undefined);
  }
}
/** 取消按钮 */
function cancel() {
  open.value = false;
  reset();
}
/** 表单重置 */
function reset() {
  form.value = {
    jobId: undefined,
    jobName: undefined,
    jobGroup: 'default',
    jobStore: 'default',
    jobExecutor: 'default',
    jobArgs: '[]',
    jobKwargs: '{}',
    invokeTarget: undefined,
    cronExpression: undefined,
    timeZone: userStore.appTimezone,
    misfireGraceTime: 1,
    coalesce: false,
    maxInstances: 1,
    status: "1"
  };
  proxy.resetForm("jobRef");
}
/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}
/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}
// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.jobId);
  single.value = selection.length != 1;
  multiple.value = !selection.length;
}
// 任务状态修改
async function handleStatusChange(row) {
  if (changingIds.has(row.jobId)) return;
  changingIds.add(row.jobId);
  let text = row.status === "0" ? "启用" : "停用";
  try {
    await proxy.$modal.confirm(`确认要${text}任务“${row.jobName}”吗？`);
    const response = await changeJobStatus(row.jobId, row.status);
    showMutationResult(response);
    await getList();
  } catch {
    row.status = row.status === "0" ? "1" : "0";
  } finally {
    changingIds.delete(row.jobId);
  }
}
/* 立即执行一次 */
async function handleRun(row) {
  if (runningIds.has(row.jobId)) return;
  runningIds.add(row.jobId);
  try {
    await proxy.$modal.confirm(`确认要立即执行一次任务“${row.jobName}”吗？`);
    const response = await runJob(row.jobId);
    proxy.$modal.msg(response.msg);
    handleRuntime('executions', row, response.data.executionId);
  } catch {
    // 用户取消或请求层已显示失败原因。
  } finally {
    runningIds.delete(row.jobId);
  }
}
/** 任务详细信息 */
function handleView(row) {
  getJob(row.jobId).then(response => {
    form.value = response.data;
    openView.value = true;
  });
}
/** cron表达式按钮操作 */
function handleShowCron() {
  expression.value = form.value.cronExpression;
  openCron.value = true;
}
/** 确定后回传值 */
function crontabFill(value) {
  form.value.cronExpression = value;
}
/** 任务日志列表查询 */
function handleJobLog(row) {
  const jobId = row.jobId || 0;
  router.push('/monitor/job-log/index/' + jobId)
}
/** 新增按钮操作 */
function handleAdd() {
  reset();
  open.value = true;
  title.value = "添加任务";
}
/** 修改按钮操作 */
function handleUpdate(row) {
  reset();
  const jobId = row.jobId || ids.value;
  getJob(jobId).then(response => {
    form.value = {
      ...response.data,
      jobArgs: JSON.stringify(response.data.jobArgs ?? [], null, 2),
      jobKwargs: JSON.stringify(response.data.jobKwargs ?? {}, null, 2)
    };
    open.value = true;
    title.value = "修改任务";
  });
}
/** 提交按钮 */
async function submitForm() {
  if (submitting.value) return;
  submitting.value = true;
  try {
    const valid = await proxy.$refs["jobRef"].validate().catch(() => false);
    if (!valid) return;
    const save = form.value.jobId != undefined ? updateJob : addJob;
    const response = await save(buildJobPayload(form.value));
    open.value = false;
    showMutationResult(response);
    await getList();
  } catch {
    // 校验或保存失败时保留表单；同步失败通过已保存响应单独展示。
  } finally {
    submitting.value = false;
  }
}
/** 删除按钮操作 */
function handleDelete(row) {
  const jobIds = row.jobId || ids.value;
  proxy.$modal.confirm('是否确认删除定时任务编号为"' + jobIds + '"的数据项?').then(function () {
    return delJob(jobIds);
  }).then(response => {
    getList();
    showMutationResult(response);
  }).catch(() => {});
}
/** 导出按钮操作 */
function handleExport() {
  proxy.download("monitor/job/export", {
    ...queryParams.value,
  }, `job_${new Date().getTime()}.xlsx`);
}

/** 停止列表刷新并取消未完成的请求 */
function stopListRefresh() {
  clearTimeout(syncRefreshTimer);
  listController?.abort();
  listVersion++;
  loading.value = false;
}

/** 处理页面显示状态变化 */
function handlePageVisibility() {
  if (document.hidden) stopListRefresh();
  else if (pageActive) getList({ silent: true });
}

onMounted(() => document.addEventListener('visibilitychange', handlePageVisibility));
onActivated(() => {
  if (!pageActive) {
    pageActive = true;
    getList();
  }
});
onDeactivated(() => {
  pageActive = false;
  stopListRefresh();
});
onBeforeUnmount(() => {
  pageActive = false;
  stopListRefresh();
  document.removeEventListener('visibilitychange', handlePageVisibility);
});
getList();
</script>

<style scoped>
.form-help {
  width: 100%;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin-top: 4px;
}
.field-unit {
  margin: 0 16px 0 8px;
}
</style>
