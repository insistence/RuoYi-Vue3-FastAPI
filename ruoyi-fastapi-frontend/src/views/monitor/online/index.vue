<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch">
         <el-form-item label="登录地址" prop="ipaddr">
            <el-input
               v-model="queryParams.ipaddr"
               placeholder="请输入登录地址"
               clearable
               style="width: 200px"
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="用户名称" prop="userName">
            <el-input
               v-model="queryParams.userName"
               placeholder="请输入用户名称"
               clearable
               style="width: 200px"
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

     <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button
               type="danger"
               plain
               icon="Remove"
               :disabled="multiple"
               @click="handleForceLogout"
               v-hasPermi="['monitor:online:batchLogout']"
            >强退</el-button>
         </el-col>

         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table
         v-loading="loading"
         :data="onlineList.slice((pageNum - 1) * pageSize, pageNum * pageSize)"
         style="width: 100%;"
         @selection-change="handleSelectionChange"
      >
<!--         <el-table-column label="序号" width="50" type="index" align="center">-->
<!--            <template #default="scope">-->
<!--               <span>{{ (pageNum - 1) * pageSize + scope.$index + 1 }}</span>-->
<!--            </template>-->
<!--         </el-table-column>-->
         <el-table-column type="selection" width="55" align="center" />
         <el-table-column label="会话编号" align="center" prop="tokenId" :show-overflow-tooltip="true" />
         <el-table-column label="登录名称" align="center" prop="userName" :show-overflow-tooltip="true" />
         <el-table-column label="所属部门" align="center" prop="deptName" :show-overflow-tooltip="true" />
         <el-table-column label="主机" align="center" prop="ipaddr" :show-overflow-tooltip="true" />
         <el-table-column label="登录地点" align="center" prop="loginLocation" :show-overflow-tooltip="true" />
         <el-table-column label="操作系统" align="center" prop="os" :show-overflow-tooltip="true" />
         <el-table-column label="浏览器" align="center" prop="browser" :show-overflow-tooltip="true" />
         <el-table-column label="登录时间" align="center" prop="loginTime" width="180">
            <template #default="scope">
               <span>{{ parseTime(scope.row.loginTime) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="操作" width="100" align="center" class-name="small-padding fixed-width">
            <template #default="scope">
              <el-tooltip content="强退" placement="top">
                <el-button link type="primary" icon="Remove" @click="handleForceLogout(scope.row)" v-hasPermi="['monitor:online:forceLogout']"></el-button>
              </el-tooltip>
            </template>
         </el-table-column>
      </el-table>

      <pagination v-show="total > 0" :total="total" v-model:page="pageNum" v-model:limit="pageSize" />
   </div>
</template>

<script setup name="Online">
import { forceLogout, list as initData } from "@/api/monitor/online";

const { proxy } = getCurrentInstance();

const onlineList = ref([]);
const loading = ref(true);
const total = ref(0);
const pageNum = ref(1);
const pageSize = ref(10);
const showSearch = ref(true);
const ids = ref([]);
const single = ref(true);
const multiple = ref(true);

const queryParams = ref({
  ipaddr: undefined,
  userName: undefined
});

/** 查询登录日志列表 */
function getList() {
  loading.value = true;
  initData(queryParams.value).then(response => {
    onlineList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}
/** 搜索按钮操作 */
function handleQuery() {
  pageNum.value = 1;
  getList();
}
/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}
/** 多选框选中数据 */
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.tokenId);
  single.value = selection.length != 1;
  multiple.value = !selection.length;
}
/** 强退按钮操作 */
function handleForceLogout(row) {
  const tokenIds = row.tokenId || ids.value;
  proxy.$modal.confirm('是否确认强退名称为"' + row.userName + '"的用户?').then(function () {
  return forceLogout(tokenIds);
  }).then(() => {
    getList();
    proxy.$modal.msgSuccess("强退成功");
  }).catch(() => {});
}

getList();
</script>
