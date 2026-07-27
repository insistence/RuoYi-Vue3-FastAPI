<template>
  <el-dialog
    title="文件详细信息"
    v-model="open"
    width="820px"
    append-to-body
  >
    <el-descriptions
      :column="2"
      border
      label-width="110px"
      class="file-descriptions"
    >
      <el-descriptions-item label="文件ID" :span="2">
        {{ detail.fileId }}
      </el-descriptions-item>
      <el-descriptions-item label="原始文件名">
        {{ detail.originalName }}
      </el-descriptions-item>
      <el-descriptions-item label="存储文件名">
        {{ detail.storedName }}
      </el-descriptions-item>
      <el-descriptions-item label="访问类型">
        {{ accessTypeLabel(detail.accessType) }}
      </el-descriptions-item>
      <el-descriptions-item label="文件状态">
        {{ statusLabel(detail.status) }}
      </el-descriptions-item>
      <el-descriptions-item label="上传用户">
        {{ detail.createBy || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="上传用户ID">
        {{ detail.uploadUserId || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="上传人权限">
        <el-tag
          v-if="detail.accessType === 'private' && detail.uploadUserId"
          :type="uploaderPermissionTagType(detail)"
          effect="plain"
        >
          {{ uploaderPermissionLabel(detail) }}
        </el-tag>
        <span v-else>{{ uploaderPermissionLabel(detail) }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="所有者">
        {{ detail.ownerName || detail.ownerUserId || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="所属部门">
        {{ detail.deptName || detail.deptId || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="存储状态">
        {{ storageStatusLabel(detail.storageStatus) }}
      </el-descriptions-item>
      <el-descriptions-item label="ACL数量">
        {{ detail.aclEntryCount || 0 }}
      </el-descriptions-item>
      <el-descriptions-item label="业务引用">
        <el-button
          v-if="detail.referenceCount"
          link
          type="primary"
          @click="emit('reference', detail)"
        >
          {{ detail.referenceCount }} 项
        </el-button>
        <span v-else>0 项</span>
      </el-descriptions-item>
      <el-descriptions-item label="权限版本">
        {{ detail.aclVersion ?? "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="文件大小">
        {{ formatFileSize(detail.fileSize) }}
      </el-descriptions-item>
      <el-descriptions-item label="内容类型">
        {{ detail.contentType || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="扩展名">
        {{ detail.extension || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="上传时间">
        {{ parseTime(detail.createTime) }}
      </el-descriptions-item>
      <el-descriptions-item label="过期时间">
        {{ parseTime(detail.expireTime) || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="移入回收站">
        {{ parseTime(detail.deletedTime) || "-" }}
      </el-descriptions-item>
      <el-descriptions-item label="存储相对路径" :span="2">
        {{ detail.storageKey }}
      </el-descriptions-item>
      <el-descriptions-item label="SHA-256" :span="2">
        <span class="file-hash">{{ detail.fileHash }}</span>
      </el-descriptions-item>
    </el-descriptions>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="open = false">关 闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {
  accessTypeLabel,
  formatFileSize,
  statusLabel,
  storageStatusLabel
} from "./fileFormatters";

defineProps({
  detail: {
    type: Object,
    default: () => ({})
  }
});

const emit = defineEmits(["reference"]);
const open = defineModel({
  type: Boolean,
  default: false
});

function uploaderPermissionLabel(file) {
  if (file.accessType !== "private") {
    return "公开文件无需单独授权";
  }
  if (!file.uploadUserId) {
    return "未记录上传人";
  }
  const accessEnabled =
    file.uploaderAccessEnabled === "1" ||
    file.uploaderAccessEnabled === true;
  if (file.uploadUserId === file.ownerUserId) {
    return accessEnabled
      ? "兼容访问已保留；同时为所有者"
      : "兼容访问已移除；仍通过所有者访问";
  }
  return accessEnabled
    ? "已保留，显式拒绝可覆盖"
    : "已移除，不再因上传身份放行";
}

function uploaderPermissionTagType(file) {
  if (
    file.uploaderAccessEnabled !== "1" &&
    file.uploaderAccessEnabled !== true
  ) {
    return "info";
  }
  return file.uploadUserId === file.ownerUserId ? "primary" : "warning";
}
</script>

<style scoped>
.file-descriptions :deep(.el-descriptions__label) {
  white-space: nowrap;
}

.file-descriptions :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.file-hash {
  word-break: break-all;
  font-family: monospace;
}
</style>
