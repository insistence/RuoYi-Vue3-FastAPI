<template>
  <el-drawer
    :title="`业务引用 - ${fileName}`"
    v-model="visible"
    size="55%"
    append-to-body
  >
    <el-alert
      title="存在业务引用时文件不能移入回收站，请先在对应业务中解除文件引用。"
      type="warning"
      :closable="false"
      show-icon
      class="mb8"
    />
    <el-table v-loading="loading" :data="referenceList">
      <el-table-column
        label="业务类型"
        align="center"
        prop="businessType"
        width="130"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="业务名称"
        align="left"
        prop="businessName"
        min-width="180"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.businessName || "-" }}</template>
      </el-table-column>
      <el-table-column
        label="业务ID"
        align="center"
        prop="businessId"
        min-width="160"
        :show-overflow-tooltip="true"
      />
      <el-table-column
        label="保留到期"
        align="center"
        prop="retentionExpireTime"
        width="180"
      >
        <template #default="scope">
          {{
            scope.row.retentionExpireTime
              ? parseTime(scope.row.retentionExpireTime)
              : "永久保留"
          }}
        </template>
      </el-table-column>
      <el-table-column label="来源" align="center" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.legacy" type="info" effect="plain">
            兼容字段
          </el-tag>
          <el-tag v-else type="success" effect="plain">引用关系</el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="登记人"
        align="center"
        prop="createBy"
        width="110"
        :show-overflow-tooltip="true"
      >
        <template #default="scope">{{ scope.row.createBy || "-" }}</template>
      </el-table-column>
      <el-table-column
        label="登记时间"
        align="center"
        prop="createTime"
        width="180"
      >
        <template #default="scope">
          {{ parseTime(scope.row.createTime) || "-" }}
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<script setup>
import { listFileReference } from "@/api/system/file";

const visible = ref(false);
const loading = ref(false);
const fileName = ref("");
const referenceList = ref([]);

function open(row) {
  fileName.value = row.originalName;
  visible.value = true;
  loading.value = true;
  listFileReference(row.fileId)
    .then(response => {
      referenceList.value = response.data;
    })
    .finally(() => {
      loading.value = false;
    });
}

defineExpose({ open });
</script>
