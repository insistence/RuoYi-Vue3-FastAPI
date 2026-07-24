<template>
  <el-drawer
    title="文件保留期限提醒"
    v-model="visible"
    size="70%"
    append-to-body
  >
    <el-alert
      title="仅对受保护文件生成提醒；文件到期后的下载限制直接按到期时间生效，不依赖提醒扫描是否按时执行。"
      type="info"
      :closable="false"
      show-icon
      class="mb8"
    />
    <el-form
      ref="queryRef"
      :model="queryParams"
      :inline="true"
      label-width="68px"
    >
      <el-form-item label="文件名称" prop="originalName">
        <el-input
          v-model="queryParams.originalName"
          placeholder="请输入原始文件名"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="提醒类型" prop="noticeType">
        <el-select
          v-model="queryParams.noticeType"
          placeholder="请选择提醒类型"
          clearable
          style="width: 200px"
        >
          <el-option label="即将到期" value="expiring" />
          <el-option label="已到期" value="expired" />
        </el-select>
      </el-form-item>
      <el-form-item label="提醒状态" prop="status">
        <el-select
          v-model="queryParams.status"
          placeholder="请选择提醒状态"
          clearable
          style="width: 200px"
        >
          <el-option label="未读" value="0" />
          <el-option label="已读" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label-width="0">
        <el-button type="primary" icon="Search" @click="handleQuery">
          搜索
        </el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Refresh"
          :loading="scanning"
          @click="handleScan"
          v-hasPermi="['system:file:edit']"
        >
          扫描
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Check"
          :disabled="!ids.length"
          @click="handleRead"
        >
          已读
        </el-button>
      </el-col>
    </el-row>
    <el-table
      v-loading="loading"
      :data="reminderList"
      @selection-change="handleSelectionChange"
    >
      <el-table-column
        type="selection"
        width="50"
        align="center"
        :selectable="row => row.status === '0'"
      />
      <el-table-column
        label="文件名称"
        align="left"
        prop="originalName"
        min-width="180"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="所有者"
        align="center"
        prop="ownerName"
        width="120"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.ownerName || "-" }}</template>
      </el-table-column>
      <el-table-column
        label="所属部门"
        align="center"
        prop="deptName"
        width="140"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.deptName || "-" }}</template>
      </el-table-column>
      <el-table-column
        label="提醒类型"
        align="center"
        prop="noticeType"
        width="110"
      >
        <template #default="scope">
          <el-tag :type="scope.row.noticeType === 'expired' ? 'danger' : 'warning'">
            {{ scope.row.noticeType === "expired" ? "已到期" : "即将到期" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="到期时间"
        align="center"
        prop="expireTime"
        width="180"
      >
        <template #default="scope">{{ parseTime(scope.row.expireTime) }}</template>
      </el-table-column>
      <el-table-column label="状态" align="center" prop="status" width="90">
        <template #default="scope">
          <el-tag :type="scope.row.status === '0' ? 'warning' : 'success'">
            {{ scope.row.status === "0" ? "未读" : "已读" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="提醒时间"
        align="center"
        prop="createTime"
        width="180"
      >
        <template #default="scope">{{ parseTime(scope.row.createTime) }}</template>
      </el-table-column>
      <el-table-column
        label="读取人"
        align="center"
        prop="readBy"
        width="110"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.readBy || "-" }}</template>
      </el-table-column>
    </el-table>
    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />
  </el-drawer>
</template>

<script setup>
import {
  listFileRetentionReminder,
  readFileRetentionReminder,
  scanFileRetentionReminder
} from "@/api/system/file";

const emit = defineEmits(["refresh"]);
const { proxy } = getCurrentInstance();
const visible = ref(false);
const loading = ref(false);
const scanning = ref(false);
const reminderList = ref([]);
const total = ref(0);
const ids = ref([]);
const queryRef = ref();
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  originalName: undefined,
  noticeType: undefined,
  status: "0"
});

function open() {
  visible.value = true;
  queryParams.pageNum = 1;
  getList();
}

function getList() {
  loading.value = true;
  listFileRetentionReminder(queryParams)
    .then(response => {
      reminderList.value = response.rows;
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
  queryRef.value?.resetFields();
  queryParams.pageNum = 1;
  getList();
}

function handleScan() {
  scanning.value = true;
  scanFileRetentionReminder()
    .then(response => {
      const { expiringCount, expiredCount } = response.data;
      proxy.$modal.msgSuccess(
        `扫描完成，新增即将到期${expiringCount}条、已到期${expiredCount}条提醒`
      );
      getList();
      emit("refresh");
    })
    .finally(() => {
      scanning.value = false;
    });
}

function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.noticeId);
}

function handleRead() {
  readFileRetentionReminder(ids.value.join(",")).then(() => {
    proxy.$modal.msgSuccess("提醒已标记为已读");
    getList();
  });
}

defineExpose({ open });
</script>
