<template>
  <div class="app-container">
    <file-search-form
      v-model:query-params="queryParams"
      v-model:date-range="dateRange"
      :show="showSearch"
      :dept-options="fileDeptOptions"
      @query="handleQuery"
      @reset="resetQuery"
    />

    <file-statistics :stats="fileStats" />

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Lock"
          :disabled="privateMultiple"
          @click="handleAcl()"
          v-hasPermi="['system:file:edit']"
        >
          授权
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Switch"
          :disabled="activeMultiple"
          @click="handleTransfer()"
          v-hasPermi="['system:file:transfer']"
        >
          转移
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="RefreshLeft"
          :disabled="restoreMultiple"
          @click="handleRestore()"
          v-hasPermi="['system:file:restore']"
        >
          恢复
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="DeleteFilled"
          :disabled="purgeMultiple"
          @click="handlePurge()"
          v-hasPermi="['system:file:purge']"
        >
          清理
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-tooltip
          :disabled="!selectedReferencedCount"
          content="所选文件存在业务引用，请先解除引用"
          placement="top"
        >
          <span>
            <el-button
              type="danger"
              plain
              icon="Delete"
              :disabled="deleteMultiple"
              @click="handleDelete()"
              v-hasPermi="['system:file:remove']"
            >
              删除
            </el-button>
          </span>
        </el-tooltip>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="info"
          plain
          icon="Timer"
          @click="retentionPolicyDrawerRef?.open()"
          v-hasPermi="['system:file:edit']"
        >
          策略
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="info"
          plain
          icon="Connection"
          @click="reconcileDrawerRef?.open()"
          v-hasPermi="['system:file:reconcile']"
        >
          对账
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="info"
          plain
          icon="Bell"
          @click="retentionReminderDrawerRef?.open()"
          v-hasPermi="['system:file:list']"
        >
          提醒
        </el-button>
      </el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        @queryTable="getList"
      />
    </el-row>

    <file-table
      :file-list="fileList"
      :loading="loading"
      @selection-change="handleSelectionChange"
      @view="handleView"
      @download="handleDownload"
      @reference="handleReference"
      @acl="handleAcl"
      @transfer="handleTransfer"
      @audit="handleAudit"
      @delete="handleDelete"
      @restore="handleRestore"
      @purge="handlePurge"
    />

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <file-detail-dialog
      v-model="detailOpen"
      :detail="detail"
      @reference="handleReference"
    />
    <file-reference-drawer ref="referenceDrawerRef" />
    <file-retention-policy-drawer ref="retentionPolicyDrawerRef" />
    <file-retention-reminder-drawer
      ref="retentionReminderDrawerRef"
      @refresh="getList"
    />
    <file-acl-drawer ref="aclDrawerRef" @refresh="getList" />
    <file-transfer-dialog ref="transferDialogRef" @refresh="getList" />
    <file-audit-drawer ref="auditDrawerRef" />
    <file-reconcile-drawer ref="reconcileDrawerRef" @refresh="getList" />
  </div>
</template>

<script setup name="File">
import {
  delFile,
  getFile,
  getFileAclDeptTree,
  getFileStats,
  listFile,
  purgeFile,
  restoreFile
} from "@/api/system/file";
import FileAclDrawer from "./components/FileAclDrawer.vue";
import FileAuditDrawer from "./components/FileAuditDrawer.vue";
import FileDetailDialog from "./components/FileDetailDialog.vue";
import FileReferenceDrawer from "./components/FileReferenceDrawer.vue";
import FileReconcileDrawer from "./components/FileReconcileDrawer.vue";
import FileRetentionPolicyDrawer from "./components/FileRetentionPolicyDrawer.vue";
import FileRetentionReminderDrawer from "./components/FileRetentionReminderDrawer.vue";
import FileSearchForm from "./components/FileSearchForm.vue";
import FileStatistics from "./components/FileStatistics.vue";
import FileTable from "./components/FileTable.vue";
import FileTransferDialog from "./components/FileTransferDialog.vue";

const { proxy } = getCurrentInstance();
const fileList = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const ids = ref([]);
const privateIds = ref([]);
const activeMultiple = ref(true);
const deleteMultiple = ref(true);
const privateMultiple = ref(true);
const restoreMultiple = ref(true);
const purgeMultiple = ref(true);
const selectedReferencedCount = ref(0);
const total = ref(0);
const dateRange = ref([]);
const detailOpen = ref(false);
const detail = ref({});
const fileDeptOptions = ref([]);
const referenceDrawerRef = ref();
const retentionPolicyDrawerRef = ref();
const retentionReminderDrawerRef = ref();
const aclDrawerRef = ref();
const transferDialogRef = ref();
const auditDrawerRef = ref();
const reconcileDrawerRef = ref();
const fileStats = reactive({
  totalCount: 0,
  totalSize: 0,
  publicSize: 0,
  privateSize: 0,
  activeCount: 0,
  deletedCount: 0,
  expiredCount: 0,
  retentionExpiringCount: 0,
  aclExpiringCount: 0
});
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  originalName: undefined,
  accessType: undefined,
  status: "active",
  createBy: undefined,
  ownerName: undefined,
  deptId: undefined,
  expirationStatus: undefined
});

/** 查询文件列表 */
function getList() {
  loading.value = true;
  const query = proxy.addDateRange({ ...queryParams }, dateRange.value);
  listFile(query)
    .then(response => {
      fileList.value = response.rows;
      total.value = response.total;
    })
    .finally(() => {
      loading.value = false;
    });
  getFileStats(query).then(response => {
    Object.assign(fileStats, response.data);
  });
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.pageNum = 1;
  getList();
}

/** 重置按钮操作 */
function resetQuery() {
  queryParams.pageNum = 1;
  getList();
}

/** 多选框选中数据 */
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.fileId);
  privateIds.value = selection
    .filter(item => item.status === "active" && item.accessType === "private")
    .map(item => item.fileId);
  selectedReferencedCount.value = selection.filter(
    item => item.referenceCount > 0
  ).length;
  activeMultiple.value =
    !selection.length || selection.some(item => item.status !== "active");
  deleteMultiple.value =
    activeMultiple.value || selectedReferencedCount.value > 0;
  privateMultiple.value = !privateIds.value.length;
  restoreMultiple.value =
    !selection.length || selection.some(item => item.status !== "deleted");
  purgeMultiple.value =
    !selection.length ||
    selection.some(item => !["deleted", "purging"].includes(item.status));
}

/** 查看文件详情 */
function handleView(row) {
  getFile(row.fileId).then(response => {
    detail.value = response.data;
    detailOpen.value = true;
  });
}

/** 下载文件 */
function handleDownload(row) {
  const displayName = encodeURIComponent(row.storedName || "file");
  proxy.$download.file(
    `/system/file/download/${row.fileId}/${displayName}`
  );
}

/** 查看文件业务引用 */
function handleReference(row) {
  referenceDrawerRef.value?.open(row);
}

/** 配置文件访问权限 */
function handleAcl(row) {
  aclDrawerRef.value?.open(row, ids.value, privateIds.value);
}

/** 转移文件 */
function handleTransfer(row) {
  transferDialogRef.value?.open(row, ids.value);
}

/** 查看文件访问审计 */
function handleAudit(row) {
  auditDrawerRef.value?.open(row);
}

/** 删除文件 */
function handleDelete(row) {
  const isSingle = row?.fileId;
  if (isSingle && row.referenceCount > 0) {
    proxy.$modal.msgWarning("文件仍被业务引用，请先解除引用后再删除");
    return;
  }
  if (!isSingle && selectedReferencedCount.value > 0) {
    proxy.$modal.msgWarning("所选文件存在业务引用，请先解除引用后再删除");
    return;
  }
  const fileIds = isSingle ? row.fileId : ids.value;
  const fileName = isSingle ? row.originalName : `${ids.value.length}个文件`;
  proxy.$modal
    .confirm(`是否确认将文件“${fileName}”移入回收站?`)
    .then(() => delFile(fileIds))
    .then(() => {
      getList();
      proxy.$modal.msgSuccess("文件已移入回收站");
    })
    .catch(() => {});
}

/** 恢复文件 */
function handleRestore(row) {
  const isSingle = row?.fileId;
  const fileIds = isSingle ? row.fileId : ids.value;
  const fileName = isSingle ? row.originalName : `${ids.value.length}个文件`;
  proxy.$modal
    .confirm(`是否确认恢复文件“${fileName}”?`)
    .then(() => restoreFile(fileIds))
    .then(() => {
      getList();
      proxy.$modal.msgSuccess("文件恢复成功");
    })
    .catch(() => {});
}

/** 永久清理文件 */
function handlePurge(row) {
  const isSingle = row?.fileId;
  const fileIds = isSingle ? row.fileId : ids.value.join(",");
  const fileName = isSingle ? row.originalName : `${ids.value.length}个文件`;
  proxy.$modal
    .confirm(`永久清理后无法恢复，是否确认清理文件“${fileName}”?`)
    .then(() => purgeFile(fileIds))
    .then(() => {
      getList();
      proxy.$modal.msgSuccess("文件已永久清理");
    })
    .catch(() => {});
}

getList();
getFileAclDeptTree().then(response => {
  fileDeptOptions.value = response.data;
});
</script>
