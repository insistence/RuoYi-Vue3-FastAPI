<template>
  <el-form
    ref="queryRef"
    v-show="show"
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
        @keyup.enter="emit('query')"
      />
    </el-form-item>
    <el-form-item label="访问类型" prop="accessType">
      <el-select
        v-model="queryParams.accessType"
        placeholder="请选择访问类型"
        clearable
        style="width: 200px"
      >
        <el-option label="公开文件" value="public" />
        <el-option label="受保护文件" value="private" />
      </el-select>
    </el-form-item>
    <el-form-item label="文件状态" prop="status">
      <el-select
        v-model="queryParams.status"
        placeholder="请选择文件状态"
        clearable
        style="width: 200px"
      >
        <el-option label="正常" value="active" />
        <el-option label="已删除" value="deleted" />
        <el-option label="清理中" value="purging" />
      </el-select>
    </el-form-item>
    <el-form-item label="上传用户" prop="createBy">
      <el-input
        v-model="queryParams.createBy"
        placeholder="请输入上传用户"
        clearable
        style="width: 200px"
        @keyup.enter="emit('query')"
      />
    </el-form-item>
    <el-form-item label="所有者" prop="ownerName">
      <el-input
        v-model="queryParams.ownerName"
        placeholder="请输入所有者"
        clearable
        style="width: 200px"
        @keyup.enter="emit('query')"
      />
    </el-form-item>
    <el-form-item label="所属部门" prop="deptId">
      <el-tree-select
        v-model="queryParams.deptId"
        :data="deptOptions"
        :props="{ value: 'id', label: 'label', children: 'children' }"
        value-key="id"
        placeholder="请选择所属部门"
        filterable
        clearable
        check-strictly
        :render-after-expand="false"
        style="width: 200px"
      />
    </el-form-item>
    <el-form-item label="过期状态" prop="expirationStatus">
      <el-select
        v-model="queryParams.expirationStatus"
        placeholder="请选择过期状态"
        clearable
        style="width: 200px"
      >
        <el-option label="永久有效" value="permanent" />
        <el-option label="有效" value="valid" />
        <el-option label="7天内过期" value="expiring" />
        <el-option label="已过期" value="expired" />
      </el-select>
    </el-form-item>
    <el-form-item label="上传时间">
      <el-date-picker
        v-model="dateRange"
        value-format="YYYY-MM-DD HH:mm:ss"
        type="datetimerange"
        style="width: 200px"
        range-separator="-"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
      />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" icon="Search" @click="emit('query')">搜索</el-button>
      <el-button icon="Refresh" @click="handleReset">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup>
defineProps({
  show: {
    type: Boolean,
    default: true
  },
  deptOptions: {
    type: Array,
    default: () => []
  }
});

const emit = defineEmits(["query", "reset"]);
const queryParams = defineModel("queryParams", {
  type: Object,
  required: true
});
const dateRange = defineModel("dateRange", {
  type: Array,
  default: () => []
});
const queryRef = ref();

function handleReset() {
  dateRange.value = [];
  queryRef.value?.resetFields();
  emit("reset");
}
</script>
