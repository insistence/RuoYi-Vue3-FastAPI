<template>
  <el-table
    v-loading="loading"
    :data="fileList"
    @selection-change="emit('selection-change', $event)"
  >
    <el-table-column type="selection" width="50" align="center" />
    <el-table-column
      label="原始文件名"
      align="left"
      prop="originalName"
      min-width="200"
      :show-overflow-tooltip="true"
    />
    <el-table-column label="访问类型" align="center" prop="accessType" width="110">
      <template #default="scope">
        <el-tag v-if="scope.row.accessType === 'public'" type="success">公开</el-tag>
        <el-tag v-else type="warning">受保护</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="扩展名" align="center" prop="extension" width="90" />
    <el-table-column label="文件大小" align="right" prop="fileSize" width="120">
      <template #default="scope">{{ formatFileSize(scope.row.fileSize) }}</template>
    </el-table-column>
    <el-table-column
      label="上传用户"
      align="center"
      prop="createBy"
      width="120"
      :show-overflow-tooltip="true"
    />
    <el-table-column
      label="所有者"
      align="center"
      prop="ownerName"
      width="120"
      :show-overflow-tooltip="true"
    >
      <template #default="scope">
        {{ scope.row.ownerName || scope.row.ownerUserId || "-" }}
      </template>
    </el-table-column>
    <el-table-column
      label="所属部门"
      align="center"
      prop="deptName"
      width="140"
      :show-overflow-tooltip="true"
    >
      <template #default="scope">
        {{ scope.row.deptName || scope.row.deptId || "-" }}
      </template>
    </el-table-column>
    <el-table-column label="文件有效期" align="center" prop="expireTime" width="150">
      <template #default="scope">
        <el-tag :type="expirationTagType(scope.row.expireTime)" effect="plain">
          {{ expirationLabel(scope.row.expireTime) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="ACL" align="center" width="130">
      <template #default="scope">
        <el-tooltip
          v-if="scope.row.aclNearestExpireTime"
          :content="`最近过期：${parseTime(scope.row.aclNearestExpireTime)}`"
          placement="top"
        >
          <el-tag
            :type="isAclExpiring(scope.row.aclNearestExpireTime) ? 'warning' : 'info'"
            effect="plain"
          >
            {{ scope.row.aclEntryCount }} 项<span
              v-if="isAclExpiring(scope.row.aclNearestExpireTime)"
            >
              · 即将过期</span
            >
          </el-tag>
        </el-tooltip>
        <span v-else>{{ scope.row.aclEntryCount || 0 }} 项</span>
      </template>
    </el-table-column>
    <el-table-column
      label="业务引用"
      align="center"
      prop="referenceCount"
      width="100"
    >
      <template #default="scope">
        <el-button
          v-if="scope.row.referenceCount"
          link
          type="primary"
          @click="emit('reference', scope.row)"
        >
          {{ scope.row.referenceCount }} 项
        </el-button>
        <span v-else>0 项</span>
      </template>
    </el-table-column>
    <el-table-column
      label="存储状态"
      align="center"
      prop="storageStatus"
      width="110"
    >
      <template #default="scope">
        <el-tag
          :type="storageStatusTagType(scope.row.storageStatus)"
          effect="plain"
        >
          {{ storageStatusLabel(scope.row.storageStatus) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="上传时间" align="center" prop="createTime" width="180">
      <template #default="scope">{{ parseTime(scope.row.createTime) }}</template>
    </el-table-column>
    <el-table-column label="状态" align="center" prop="status" width="90">
      <template #default="scope">
        <el-tag v-if="scope.row.status === 'active'" type="success">正常</el-tag>
        <el-tag v-else-if="scope.row.status === 'deleted'" type="info">
          已删除
        </el-tag>
        <el-tag v-else type="warning">清理中</el-tag>
      </template>
    </el-table-column>
    <el-table-column
      label="操作"
      align="center"
      class-name="small-padding fixed-width"
      width="250"
      fixed="right"
    >
      <template #default="scope">
        <el-tooltip content="详细" placement="top">
          <el-button
            link
            type="primary"
            icon="View"
            @click="emit('view', scope.row)"
            v-hasPermi="['system:file:query']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="scope.row.status === 'active'"
          content="下载"
          placement="top"
        >
          <el-button
            link
            type="primary"
            icon="Download"
            @click="emit('download', scope.row)"
            v-hasPermi="['system:file:download']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="
            scope.row.accessType === 'private' && scope.row.status === 'active'
          "
          content="授权"
          placement="top"
        >
          <el-button
            link
            type="primary"
            icon="Lock"
            @click="emit('acl', scope.row)"
            v-hasPermi="['system:file:edit']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="scope.row.status === 'active'"
          content="转移"
          placement="top"
        >
          <el-button
            link
            type="primary"
            icon="Switch"
            @click="emit('transfer', scope.row)"
            v-hasPermi="['system:file:transfer']"
          />
        </el-tooltip>
        <el-tooltip content="审计" placement="top">
          <el-button
            link
            type="primary"
            icon="Tickets"
            @click="emit('audit', scope.row)"
            v-hasPermi="['system:file:query']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="scope.row.status === 'active' && scope.row.referenceCount"
          content="存在业务引用，无法删除"
          placement="top"
        >
          <span class="file-action-disabled-wrapper">
            <el-button
              link
              type="danger"
              icon="Delete"
              disabled
              v-hasPermi="['system:file:remove']"
            />
          </span>
        </el-tooltip>
        <el-tooltip
          v-else-if="scope.row.status === 'active'"
          content="删除"
          placement="top"
        >
          <el-button
            link
            type="danger"
            icon="Delete"
            @click="emit('delete', scope.row)"
            v-hasPermi="['system:file:remove']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="scope.row.status === 'deleted'"
          content="恢复"
          placement="top"
        >
          <el-button
            link
            type="success"
            icon="RefreshLeft"
            @click="emit('restore', scope.row)"
            v-hasPermi="['system:file:restore']"
          />
        </el-tooltip>
        <el-tooltip
          v-if="scope.row.status !== 'active'"
          :content="
            scope.row.status === 'purging' ? '重试永久清理' : '永久清理'
          "
          placement="top"
        >
          <el-button
            link
            type="danger"
            icon="DeleteFilled"
            @click="emit('purge', scope.row)"
            v-hasPermi="['system:file:purge']"
          />
        </el-tooltip>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import {
  expirationLabel,
  expirationTagType,
  formatFileSize,
  isAclExpiring,
  storageStatusLabel,
  storageStatusTagType
} from "./fileFormatters";

defineProps({
  fileList: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits([
  "selection-change",
  "view",
  "download",
  "reference",
  "acl",
  "transfer",
  "audit",
  "delete",
  "restore",
  "purge"
]);
</script>

<style scoped>
.file-action-disabled-wrapper {
  display: inline-flex;
  align-items: center;
  margin-left: 12px;
  vertical-align: middle;
}
</style>
