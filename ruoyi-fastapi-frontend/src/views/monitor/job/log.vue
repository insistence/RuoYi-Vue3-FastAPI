<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
         <el-form-item label="任务名称" prop="jobName">
            <el-input
               v-model="queryParams.jobName"
               placeholder="请输入任务名称"
               clearable
               style="width: 240px"
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="业务分组" prop="jobGroup">
            <el-input v-model="queryParams.jobGroup" placeholder="请输入业务分组" clearable style="width: 240px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="任务编号" prop="jobId">
            <el-input v-model="queryParams.jobId" placeholder="精确匹配任务ID" clearable style="width: 240px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="执行编号" prop="executionId">
            <el-input v-model="queryParams.executionId" placeholder="精确匹配执行ID" clearable style="width: 240px" @keyup.enter="handleQuery" />
         </el-form-item>
         <el-form-item label="执行状态" prop="status">
            <el-select
               v-model="queryParams.status"
               placeholder="请选择执行状态"
               clearable
               style="width: 240px"
            >
               <el-option
                  v-for="dict in sys_common_status"
                  :key="dict.value"
                  :label="dict.label"
                  :value="dict.value"
               />
            </el-select>
         </el-form-item>
         <el-form-item label="执行时间" style="width: 308px">
            <el-date-picker
               v-model="dateRange"
               value-format="YYYY-MM-DD"
               type="daterange"
               :aria-label="`日期范围（${getDisplayTimezone()}）`"
               range-separator="-"
               start-placeholder="开始日期"
               end-placeholder="结束日期"
            ></el-date-picker>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
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
               type="danger"
               plain
               icon="Delete"
               @click="handleClean"
               v-hasPermi="['monitor:job:remove']"
            >清空</el-button>
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
               type="warning" 
               plain 
               icon="Close"
               @click="handleClose"
            >关闭</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="jobLogList" @selection-change="handleSelectionChange">
         <el-table-column type="selection" width="55" align="center" />
         <el-table-column label="日志编号" width="80" align="center" prop="jobLogId" />
         <el-table-column label="任务编号" width="90" align="center" prop="jobId" />
         <el-table-column label="任务名称" align="center" prop="jobName" :show-overflow-tooltip="true" />
         <el-table-column label="业务分组" align="center" prop="jobGroup" :show-overflow-tooltip="true">
            <template #default="scope">
               {{ scope.row.jobGroup }}
            </template>
         </el-table-column>
         <el-table-column label="调用目标字符串" align="center" prop="invokeTarget" :show-overflow-tooltip="true" />
         <el-table-column label="日志信息" align="center" prop="jobMessage" :show-overflow-tooltip="true" />
         <el-table-column label="执行状态" align="center" prop="status">
            <template #default="scope">
               <dict-tag :options="sys_common_status" :value="scope.row.status" />
            </template>
         </el-table-column>
         <el-table-column label="执行时间" align="center" prop="createTime" width="180">
            <template #default="scope">
               <span>{{ parseTime(scope.row.createTime) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
            <template #default="scope">
               <el-button link type="primary" icon="View" @click="handleView(scope.row)" v-hasPermi="['monitor:job:query']">详细</el-button>
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

      <!-- 调度日志详细 -->
      <job-detail v-model:visible="open" :row="form" type="log" />
   </div>
</template>

<script setup name="JobLog">
import { getDisplayTimezone } from '@/utils/time';
import JobDetail from './detail'
import { listJobLog, delJobLog, cleanJobLog } from "@/api/monitor/jobLog";

const { proxy } = getCurrentInstance();
const { sys_common_status } = proxy.useDict("sys_common_status");

const jobLogList = ref([]);
const open = ref(false);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const multiple = ref(true);
const total = ref(0);
const dateRange = ref([]);
const route = useRoute();

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    jobId: undefined,
    executionId: undefined,
    jobName: undefined,
    jobGroup: undefined,
    status: undefined
  }
});

const { queryParams, form, rules } = toRefs(data);

/** 查询调度日志列表 */
function getList() {
  loading.value = true;
  const query = {
    ...queryParams.value,
    jobId: queryParams.value.jobId || undefined,
    executionId: queryParams.value.executionId || undefined
  };
  listJobLog(proxy.addDateRange(query, dateRange.value)).then(response => {
    jobLogList.value = response.rows;
    total.value = response.total;
  }).finally(() => {
    loading.value = false;
  });
}
// 返回按钮
function handleClose() {
  const obj = { path: "/monitor/job" };
  proxy.$tab.closeOpenPage(obj);
}
/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
  getList();
}
/** 重置按钮操作 */
function resetQuery() {
  dateRange.value = [];
  proxy.resetForm("queryRef");
  handleQuery();
}
// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.jobLogId);
  multiple.value = !selection.length;
}
/** 详细按钮操作 */
function handleView(row) {
  open.value = true;
  form.value = row;
}
/** 删除按钮操作 */
function handleDelete(row) {
  proxy.$modal.confirm('是否确认删除调度日志编号为"' + ids.value + '"的数据项?').then(function () {
    return delJobLog(ids.value);
  }).then(() => {
    getList();
    proxy.$modal.msgSuccess("删除成功");
  }).catch(() => {});
}
/** 清空按钮操作 */
function handleClean() {
  proxy.$modal.confirm("是否确认清空所有调度日志数据项?").then(function () {
    return cleanJobLog();
  }).then(() => {
    getList();
    proxy.$modal.msgSuccess("清空成功");
  }).catch(() => {});
}
/** 导出按钮操作 */
function handleExport() {
  proxy.download("monitor/jobLog/export", proxy.addDateRange({
    ...queryParams.value,
    jobId: queryParams.value.jobId || undefined,
    executionId: queryParams.value.executionId || undefined
  }, dateRange.value), `job_log_${new Date().getTime()}.xlsx`);
}

// 使用稳定编号查询，任务改名或删除后仍能查看执行日志。
watch(() => [route.params.jobId, route.query.executionId], ([jobId, executionId]) => {
  queryParams.value.jobId = jobId && jobId != 0 ? jobId : undefined;
  queryParams.value.executionId = executionId || undefined;
  queryParams.value.jobName = undefined;
  queryParams.value.jobGroup = undefined;
  handleQuery();
}, { immediate: true });
// 时区变化后重新查询日期范围，保留正在编辑的表单。
watch(getDisplayTimezone, () => {
  if (dateRange.value?.length) {
    handleQuery();
  }
});
</script>
