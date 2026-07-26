<template>
  <el-drawer
    title="文件保留策略"
    v-model="visible"
    size="900px"
    append-to-body
  >
    <el-alert
      title="策略仅应用于后续新建或重建的业务引用；未配置或已停用的业务类型永久保留，既有引用不会被追溯修改。"
      type="info"
      :closable="false"
      show-icon
      class="mb8"
    />
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd">
          新增
        </el-button>
      </el-col>
    </el-row>
    <el-table v-loading="loading" :data="policyList">
      <el-table-column
        label="业务类型"
        align="center"
        prop="businessType"
        min-width="140"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="保留天数"
        align="center"
        prop="retentionDays"
        width="100"
      />
      <el-table-column label="状态" align="center" prop="status" width="90">
        <template #default="scope">
          <el-tag :type="scope.row.status === '0' ? 'success' : 'info'">
            {{ scope.row.status === "0" ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="备注"
        align="left"
        prop="remark"
        min-width="160"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.remark || "-" }}</template>
      </el-table-column>
      <el-table-column
        label="更新时间"
        align="center"
        prop="updateTime"
        width="180"
      >
        <template #default="scope">
          {{ parseTime(scope.row.updateTime) || "-" }}
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="90" fixed="right">
        <template #default="scope">
          <el-tooltip content="修改" placement="top">
            <el-button
              link
              type="primary"
              icon="Edit"
              @click="handleEdit(scope.row)"
            />
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button
              link
              type="danger"
              icon="Delete"
              @click="handleDelete(scope.row)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>

  <el-dialog
    :title="formTitle"
    v-model="formOpen"
    width="520px"
    append-to-body
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="90px"
    >
      <el-form-item label="业务类型" prop="businessType">
        <el-input
          v-model="form.businessType"
          :disabled="editing"
          maxlength="50"
          placeholder="请输入业务类型"
        />
      </el-form-item>
      <el-form-item label="保留天数" prop="retentionDays">
        <el-input-number
          v-model="form.retentionDays"
          controls-position="right"
          :min="1"
          :max="36500"
          :precision="0"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-radio-group v-model="form.status">
          <el-radio value="0">启用</el-radio>
          <el-radio value="1">停用</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="备注" prop="remark">
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入备注"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="saving" @click="submit">
          确 定
        </el-button>
        <el-button @click="formOpen = false">取 消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {
  addFileRetentionPolicy,
  delFileRetentionPolicy,
  listFileRetentionPolicy,
  updateFileRetentionPolicy
} from "@/api/system/file";

const { proxy } = getCurrentInstance();
const visible = ref(false);
const loading = ref(false);
const policyList = ref([]);
const formOpen = ref(false);
const editing = ref(false);
const saving = ref(false);
const formRef = ref();
const formTitle = computed(() =>
  editing.value ? "修改文件保留策略" : "新增文件保留策略"
);
const form = reactive({
  businessType: undefined,
  retentionDays: 30,
  status: "0",
  remark: undefined
});
const rules = {
  businessType: [{ required: true, message: "请输入业务类型", trigger: "blur" }],
  retentionDays: [{ required: true, message: "请输入保留天数", trigger: "blur" }]
};

function open() {
  visible.value = true;
  getList();
}

function getList() {
  loading.value = true;
  listFileRetentionPolicy()
    .then(response => {
      policyList.value = response.data;
    })
    .finally(() => {
      loading.value = false;
    });
}

function resetForm() {
  Object.assign(form, {
    businessType: undefined,
    retentionDays: 30,
    status: "0",
    remark: undefined
  });
  nextTick(() => formRef.value?.clearValidate());
}

function handleAdd() {
  editing.value = false;
  resetForm();
  formOpen.value = true;
}

function handleEdit(row) {
  editing.value = true;
  Object.assign(form, {
    businessType: row.businessType,
    retentionDays: row.retentionDays,
    status: row.status,
    remark: row.remark
  });
  formOpen.value = true;
  nextTick(() => formRef.value?.clearValidate());
}

function submit() {
  formRef.value.validate(valid => {
    if (!valid) return;
    saving.value = true;
    const submitRequest = editing.value
      ? updateFileRetentionPolicy(form)
      : addFileRetentionPolicy(form);
    submitRequest
      .then(() => {
        proxy.$modal.msgSuccess(editing.value ? "修改成功" : "新增成功");
        formOpen.value = false;
        getList();
      })
      .finally(() => {
        saving.value = false;
      });
  });
}

function handleDelete(row) {
  proxy.$modal
    .confirm(`是否确认删除业务类型“${row.businessType}”的保留策略?`)
    .then(() => delFileRetentionPolicy(row.businessType))
    .then(() => {
      proxy.$modal.msgSuccess("删除成功");
      getList();
    })
    .catch(() => {});
}

defineExpose({ open });
</script>
