<template>
  <!-- 创建表 -->
  <el-dialog
    title="创建表"
    :visible.sync="visible"
    width="800px"
    top="5vh"
    append-to-body
  >
    <el-form label-width="80px">
      <el-form-item
        label="数据源"
        required
      >
        <el-select
          v-model="dataSourceName"
          placeholder="请选择数据源"
          filterable
          style="width: 260px"
        >
          <el-option
            v-for="source in dataSources"
            :key="source.name"
            :label="source.name + '（' + source.dbType + '）'"
            :value="source.name"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <span>创建表语句(支持多个建表语句)：</span>
    <el-input
      type="textarea"
      :rows="10"
      placeholder="请输入文本"
      v-model="content"
    ></el-input>
    <div
      slot="footer"
      class="dialog-footer"
    >
      <el-button
        type="primary"
        @click="handleCreateTable"
        >确 定</el-button
      >
      <el-button @click="visible = false">取 消</el-button>
    </div>
  </el-dialog>
</template>

<script>
import { createTable } from '@/api/tool/gen'
export default {
  props: {
    dataSources: {
      type: Array,
      default: () => [],
    },
  },
  data() {
    return {
      // 遮罩层
      visible: false,
      // 文本内容
      content: '',
      // 目标数据源
      dataSourceName: '',
    }
  },
  methods: {
    // 显示弹框
    show() {
      this.visible = true
      const defaultSource =
        this.dataSources.find((source) => source.isDefault) || this.dataSources[0]
      this.dataSourceName = defaultSource ? defaultSource.name : ''
    },
    /** 创建按钮操作 */
    handleCreateTable() {
      if (this.content === '') {
        this.$modal.msgError('请输入建表语句')
        return
      }
      if (!this.dataSourceName) {
        this.$modal.msgError('请选择数据源')
        return
      }
      createTable({ sql: this.content, dataSourceName: this.dataSourceName }).then((res) => {
        this.$modal.msgSuccess(res.msg)
        if (res.code === 200) {
          this.visible = false
          this.$emit('ok')
        }
      })
    },
  },
}
</script>
