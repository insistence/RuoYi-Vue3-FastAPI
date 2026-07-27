<template>
  <el-drawer
    title="文件保留期限提醒"
    v-model="visible"
    size="70%"
    append-to-body
  >
    <el-alert
      title="到期前可延长保留期限；到期后仅在全部业务引用均已到期时才可移入回收站，处置会解除这些业务引用。"
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
        label="业务引用"
        align="center"
        prop="referenceCount"
        width="90"
      />
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
      <el-table-column
        label="操作"
        align="center"
        width="100"
        fixed="right"
      >
        <template #default="scope">
          <el-tooltip content="延长保留期限" placement="top">
            <el-button
              link
              type="primary"
              icon="Clock"
              @click="handleExtend(scope.row)"
              v-hasPermi="['system:file:edit']"
            />
          </el-tooltip>
          <el-tooltip
            v-if="isExpired(scope.row)"
            :content="
              scope.row.canDispose
                ? '移入回收站'
                : '存在永久或尚未到期的业务引用，暂不可处置'
            "
            placement="top"
          >
            <span>
              <el-button
                link
                type="danger"
                icon="Delete"
                :disabled="!scope.row.canDispose"
                @click="handleDispose(scope.row)"
                v-hasPermi="['system:file:remove']"
              />
            </span>
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
  </el-drawer>

  <el-dialog
    title="延长文件保留期限"
    v-model="extendOpen"
    width="520px"
    append-to-body
  >
    <el-form
      ref="extendRef"
      :model="extendForm"
      :rules="extendRules"
      label-width="92px"
    >
      <el-form-item label="文件名称">
        <span>{{ currentRow.originalName }}</span>
      </el-form-item>
      <el-form-item label="原到期时间">
        <span>{{ parseTime(currentRow.expireTime) }}</span>
      </el-form-item>
      <el-form-item label="新到期时间" prop="expireTime">
        <el-date-picker
          v-model="extendForm.expireTime"
          type="datetime"
          value-format="YYYY-MM-DD HH:mm:ss"
          placeholder="请选择新的到期时间"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="延期原因" prop="reason">
        <el-input
          v-model="extendForm.reason"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入延期原因"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="submitting" @click="submitExtend">
          确 定
        </el-button>
        <el-button @click="extendOpen = false">取 消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {
  disposeExpiredFile,
  extendFileRetention,
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
const extendRef = ref();
const extendOpen = ref(false);
const submitting = ref(false);
const currentRow = ref({});
const extendForm = reactive({
  expireTime: undefined,
  reason: undefined
});
const extendRules = {
  expireTime: [
    { required: true, message: "新的到期时间不能为空", trigger: "change" }
  ],
  reason: [
    { required: true, message: "延期原因不能为空", trigger: "blur" }
  ]
};
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

function isExpired(row) {
  return new Date(row.expireTime).getTime() <= Date.now();
}

function handleExtend(row) {
  currentRow.value = row;
  Object.assign(extendForm, {
    expireTime: defaultExtendTime(row.expireTime),
    reason: undefined
  });
  extendOpen.value = true;
  nextTick(() => extendRef.value?.clearValidate());
}

function submitExtend() {
  extendRef.value.validate(valid => {
    if (!valid) return;
    submitting.value = true;
    extendFileRetention(currentRow.value.noticeId, extendForm)
      .then(() => {
        proxy.$modal.msgSuccess("文件保留期限已延长");
        extendOpen.value = false;
        getList();
        emit("refresh");
      })
      .finally(() => {
        submitting.value = false;
      });
  });
}

function handleDispose(row) {
  proxy
    .$prompt(
      `处置后“${row.originalName}”将移入回收站，并解除${row.referenceCount || 0}条已到期业务引用。请输入处置原因：`,
      "到期文件处置",
      {
        confirmButtonText: "确定处置",
        cancelButtonText: "取消",
        closeOnClickModal: false,
        inputType: "textarea",
        inputPlaceholder: "请输入处置原因",
        inputValidator: value => {
          const reason = value?.trim();
          if (!reason) return "处置原因不能为空";
          if (reason.length > 500) return "处置原因不能超过500个字符";
          return true;
        }
      }
    )
    .then(({ value }) => {
      disposeExpiredFile(row.noticeId, { reason: value.trim() }).then(() => {
        proxy.$modal.msgSuccess("到期文件已移入回收站");
        getList();
        emit("refresh");
      });
    })
    .catch(() => {});
}

function defaultExtendTime(expireTime) {
  const baseTime = Math.max(Date.now(), new Date(expireTime).getTime());
  const target = new Date(baseTime + 30 * 24 * 60 * 60 * 1000);
  const pad = value => String(value).padStart(2, "0");
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(
    target.getDate()
  )} ${pad(target.getHours())}:${pad(target.getMinutes())}:${pad(
    target.getSeconds()
  )}`;
}

defineExpose({ open });
</script>
