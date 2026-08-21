<template>
  <!-- 创建表 -->
  <el-dialog title="创建表" v-model="visible" width="800px" top="5vh" append-to-body>
    <el-form label-width="80px">
      <el-form-item label="数据源" required>
        <el-select
          v-model="dataSourceName"
          placeholder="请选择数据源"
          filterable
          style="width: 260px"
        >
          <el-option
            v-for="source in props.dataSources"
            :key="source.name"
            :label="source.name + '（' + source.dbType + '）'"
            :value="source.name"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <span>创建表语句(支持多个建表语句)：</span>
    <el-input type="textarea" :rows="10" placeholder="请输入文本" v-model="content"></el-input>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" @click="handleImportTable">确 定</el-button>
        <el-button @click="visible = false">取 消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { createTable } from "@/api/tool/gen";

const visible = ref(false);
const content = ref("");
const dataSourceName = ref("");
const { proxy } = getCurrentInstance();
const props = defineProps({
  dataSources: {
    type: Array,
    default: () => []
  }
});
const emit = defineEmits(["ok"]);

/** 显示弹框 */
function show() {
  visible.value = true;
  const defaultSource = props.dataSources.find(source => source.isDefault) || props.dataSources[0];
  dataSourceName.value = defaultSource?.name || "";
}

/** 导入按钮操作 */
function handleImportTable() {
  if (content.value === "") {
    proxy.$modal.msgError("请输入建表语句");
    return;
  }
  if (!dataSourceName.value) {
    proxy.$modal.msgError("请选择数据源");
    return;
  }
  createTable({ sql: content.value, dataSourceName: dataSourceName.value }).then(res => {
    proxy.$modal.msgSuccess(res.msg);
    if (res.code === 200) {
      visible.value = false;
      emit("ok");
    }
  });
}

defineExpose({
  show,
});
</script>
