<template>
  <el-form
    ref="queryForm"
    v-show="show"
    :model="queryParams"
    size="small"
    :inline="true"
    label-width="68px"
  >
    <el-form-item
      label="文件名称"
      prop="originalName"
    >
      <el-input
        v-model="queryParams.originalName"
        placeholder="请输入原始文件名"
        clearable
        style="width: 200px"
        @keyup.enter.native="$emit('query')"
      />
    </el-form-item>
    <el-form-item
      label="访问类型"
      prop="accessType"
    >
      <el-select
        v-model="queryParams.accessType"
        placeholder="请选择访问类型"
        clearable
        style="width: 200px"
      >
        <el-option
          label="公开文件"
          value="public"
        />
        <el-option
          label="受保护文件"
          value="private"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      label="文件状态"
      prop="status"
    >
      <el-select
        v-model="queryParams.status"
        placeholder="请选择文件状态"
        clearable
        style="width: 200px"
      >
        <el-option
          label="正常"
          value="active"
        />
        <el-option
          label="已删除"
          value="deleted"
        />
        <el-option
          label="清理中"
          value="purging"
        />
      </el-select>
    </el-form-item>
    <el-form-item
      label="上传用户"
      prop="createBy"
    >
      <el-input
        v-model="queryParams.createBy"
        placeholder="请输入上传用户"
        clearable
        style="width: 200px"
        @keyup.enter.native="$emit('query')"
      />
    </el-form-item>
    <el-form-item
      label="所有者"
      prop="ownerName"
    >
      <el-input
        v-model="queryParams.ownerName"
        placeholder="请输入所有者"
        clearable
        style="width: 200px"
        @keyup.enter.native="$emit('query')"
      />
    </el-form-item>
    <el-form-item
      label="所属部门"
      prop="deptId"
    >
      <treeselect
        v-model="queryParams.deptId"
        :options="deptOptions"
        placeholder="请选择所属部门"
        :normalizer="normalizer"
        :clearable="true"
        :searchable="true"
        style="width: 200px"
      />
    </el-form-item>
    <el-form-item
      label="过期状态"
      prop="expirationStatus"
    >
      <el-select
        v-model="queryParams.expirationStatus"
        placeholder="请选择过期状态"
        clearable
        style="width: 200px"
      >
        <el-option
          label="永久有效"
          value="permanent"
        />
        <el-option
          label="有效"
          value="valid"
        />
        <el-option
          label="7天内过期"
          value="expiring"
        />
        <el-option
          label="已过期"
          value="expired"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="上传时间">
      <el-date-picker
        :value="dateRange"
        value-format="yyyy-MM-dd HH:mm:ss"
        type="datetimerange"
        style="width: 200px"
        range-separator="-"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        @input="$emit('update:dateRange', $event)"
      />
    </el-form-item>
    <el-form-item>
      <el-button
        type="primary"
        icon="el-icon-search"
        size="mini"
        @click="$emit('query')"
        >搜索</el-button
      >
      <el-button
        icon="el-icon-refresh"
        size="mini"
        @click="handleReset"
        >重置</el-button
      >
    </el-form-item>
  </el-form>
</template>

<script>
import Treeselect from '@riophae/vue-treeselect'
import '@riophae/vue-treeselect/dist/vue-treeselect.css'

export default {
  name: 'FileSearchForm',
  components: { Treeselect },
  props: {
    show: {
      type: Boolean,
      default: true,
    },
    queryParams: {
      type: Object,
      required: true,
    },
    dateRange: {
      type: Array,
      default: () => [],
    },
    deptOptions: {
      type: Array,
      default: () => [],
    },
  },
  methods: {
    normalizer(node) {
      return {
        id: node.id,
        label: node.label,
        children: node.children,
      }
    },
    handleReset() {
      this.$emit('update:dateRange', [])
      this.$refs.queryForm.resetFields()
      this.$emit('reset')
    },
  },
}
</script>
