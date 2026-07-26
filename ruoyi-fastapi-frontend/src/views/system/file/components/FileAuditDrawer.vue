<template>
  <el-drawer
    :title="`文件审计 - ${fileName}`"
    v-model="visible"
    size="80%"
    append-to-body
    @closed="detailOpen = false"
  >
    <el-form
      ref="queryRef"
      :model="queryParams"
      :inline="true"
      label-width="68px"
    >
      <el-form-item label="操作类型" prop="action">
        <el-select
          v-model="queryParams.action"
          placeholder="全部操作"
          clearable
          style="width: 200px"
        >
          <el-option label="上传" value="upload" />
          <el-option label="下载" value="download" />
          <el-option label="授权变更" value="acl_update" />
          <el-option label="归属转移" value="transfer" />
          <el-option label="移入回收站" value="delete" />
          <el-option label="恢复" value="restore" />
          <el-option label="永久清理" value="purge" />
          <el-option label="存储对账" value="reconcile" />
          <el-option label="保留延期" value="retention_extend" />
          <el-option label="到期处置" value="retention_dispose" />
        </el-select>
      </el-form-item>
      <el-form-item label="操作结果" prop="result">
        <el-select
          v-model="queryParams.result"
          placeholder="全部结果"
          clearable
          style="width: 200px"
        >
          <el-option label="已授权" value="allowed" />
          <el-option label="已拒绝" value="denied" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
        </el-select>
      </el-form-item>
      <el-form-item label="操作用户" prop="actorName">
        <el-input
          v-model="queryParams.actorName"
          placeholder="请输入用户名"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="操作时间">
        <el-date-picker
          v-model="dateRange"
          value-format="YYYY-MM-DD HH:mm:ss"
          type="datetimerange"
          range-separator="-"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          style="width: 200px"
        />
      </el-form-item>
      <el-form-item label-width="0">
        <el-button type="primary" icon="Search" @click="handleQuery">
          搜索
        </el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>
    <el-table v-loading="loading" :data="auditList">
      <el-table-column label="操作" align="center" prop="action" width="105">
        <template #default="scope">{{ actionLabel(scope.row.action) }}</template>
      </el-table-column>
      <el-table-column label="结果" align="center" prop="result" width="100">
        <template #default="scope">
          <el-tag :type="resultTagType(scope.row.result)">
            {{ resultLabel(scope.row.result) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="操作用户"
        align="center"
        prop="actorName"
        width="120"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="客户端地址"
        align="center"
        prop="ipAddress"
        width="140"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="传输字节"
        align="right"
        prop="bytesSent"
        width="110"
      >
        <template #default="scope">
          {{ scope.row.bytesSent ? formatFileSize(scope.row.bytesSent) : "-" }}
        </template>
      </el-table-column>
      <el-table-column
        label="失败原因"
        align="left"
        prop="errorMessage"
        min-width="140"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="访问时间"
        align="center"
        prop="accessTime"
        width="180"
      >
        <template #default="scope">{{ parseTime(scope.row.accessTime) }}</template>
      </el-table-column>
      <el-table-column label="详情" align="center" width="70">
        <template #default="scope">
          <el-tooltip content="查看审计详情" placement="top">
            <el-button
              link
              type="primary"
              icon="View"
              @click="handleDetail(scope.row)"
            />
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
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="visible = false">关 闭</el-button>
      </div>
    </template>
  </el-drawer>

  <el-dialog
    title="审计详情"
    v-model="detailOpen"
    width="720px"
    append-to-body
  >
    <el-descriptions
      :column="2"
      border
      label-width="110px"
      class="audit-descriptions"
    >
      <el-descriptions-item label="操作类型">
        {{ actionLabel(detail.action) }}
      </el-descriptions-item>
      <el-descriptions-item label="操作结果">
        {{ resultLabel(detail.result) }}
      </el-descriptions-item>
      <el-descriptions-item label="操作用户">
        {{ detail.actorName || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="客户端地址">
        {{ detail.ipAddress || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="请求ID">
        {{ detail.requestId || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="链路ID">
        {{ detail.traceId || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="操作时间" :span="2">
        {{ parseTime(detail.accessTime) }}
      </el-descriptions-item>
      <el-descriptions-item label="用户代理" :span="2">
        {{ detail.userAgent || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="失败原因" :span="2">
        {{ detail.errorMessage || "-" }}
      </el-descriptions-item>
    </el-descriptions>
    <el-table
      v-if="detailEntries.length"
      :data="detailEntries"
      border
      class="mt20"
    >
      <el-table-column label="详情项" prop="label" width="180" />
      <el-table-column
        label="内容"
        prop="value"
        :show-overflow-tooltip="true"
      />
    </el-table>
    <el-empty v-else description="无操作详情" :image-size="60" />
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="detailOpen = false">关 闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { listFileAccessLog } from "@/api/system/file";
import {
  actionLabel,
  formatFileSize,
  parseOperationDetail,
  resultLabel,
  resultTagType
} from "./fileFormatters";

const { proxy } = getCurrentInstance();
const visible = ref(false);
const loading = ref(false);
const fileId = ref("");
const fileName = ref("");
const auditList = ref([]);
const total = ref(0);
const dateRange = ref([]);
const queryRef = ref();
const detailOpen = ref(false);
const detail = ref({});
const detailEntries = computed(() =>
  parseOperationDetail(detail.value.operationDetail)
);
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  action: undefined,
  result: undefined,
  actorName: undefined
});

function open(row) {
  fileId.value = row.fileId;
  fileName.value = row.originalName;
  Object.assign(queryParams, {
    pageNum: 1,
    action: undefined,
    result: undefined,
    actorName: undefined
  });
  dateRange.value = [];
  visible.value = true;
  getList();
}

function getList() {
  loading.value = true;
  listFileAccessLog(
    fileId.value,
    proxy.addDateRange({ ...queryParams }, dateRange.value)
  )
    .then(response => {
      auditList.value = response.rows;
      total.value = response.total;
    })
    .finally(() => {
      loading.value = false;
    });
}

function handleQuery() {
  queryParams.pageNum = 1;
  getList();
}

function resetQuery() {
  dateRange.value = [];
  queryRef.value?.resetFields();
  queryParams.pageNum = 1;
  getList();
}

function handleDetail(row) {
  detail.value = row;
  detailOpen.value = true;
}

defineExpose({ open });
</script>

<style scoped>
.audit-descriptions :deep(.el-descriptions__label) {
  white-space: nowrap;
}

.audit-descriptions :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
  word-break: break-word;
}
</style>
