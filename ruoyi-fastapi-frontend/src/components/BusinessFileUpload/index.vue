<template>
  <div class="business-file-upload">
    <el-upload
      v-if="!disabled"
      ref="fileUploadRef"
      multiple
      :show-file-list="false"
      :before-upload="handleBeforeUpload"
      :http-request="handleUploadRequest"
      :on-success="handleUploadSuccess"
      :on-error="handleUploadError"
    >
      <el-button type="primary">选择文件</el-button>
    </el-upload>
    <div v-if="showTip && !disabled" class="el-upload__tip">
      请上传
      <template v-if="fileSize">
        大小不超过 <b class="upload-tip-emphasis">{{ fileSize }}MB</b>
      </template>
      <template v-if="fileType.length">
        格式为 <b class="upload-tip-emphasis">{{ fileType.join("/") }}</b>
      </template>
      的文件，最多上传 {{ limit }} 个
    </div>

    <ul
      v-if="fileList.length"
      ref="uploadFileListRef"
      class="business-file-list el-upload-list el-upload-list--text"
    >
      <li
        v-for="file in fileList"
        :key="file.fileId"
        class="el-upload-list__item business-file-item"
      >
        <div class="business-file-main">
          <span class="business-file-name" :title="file.name">{{
            file.name
          }}</span>
          <el-tag size="small" type="success">已上传</el-tag>
        </div>
        <div class="business-file-actions">
          <el-link
            :underline="false"
            type="primary"
            @click="handleDownload(file)"
          >
            下载
          </el-link>
          <el-link
            v-if="!disabled"
            :underline="false"
            type="danger"
            @click="handleDelete(file.fileId)"
          >
            删除
          </el-link>
        </div>
      </li>
    </ul>

    <ul
      v-if="pendingFileList.length"
      class="business-file-list el-upload-list el-upload-list--text"
    >
      <li
        v-for="file in pendingFileList"
        :key="file.uid"
        class="el-upload-list__item business-file-item"
      >
        <div class="business-file-main">
          <span class="business-file-name" :title="file.name">{{
            file.name
          }}</span>
          <el-tag v-if="file.status === 'uploading'" size="small"
            >上传中</el-tag
          >
          <el-tooltip v-else :content="file.error" placement="top">
            <el-tag size="small" type="danger">上传失败</el-tag>
          </el-tooltip>
        </div>
        <div v-if="file.status === 'failed'" class="business-file-actions">
          <el-link
            v-if="!disabled"
            :underline="false"
            type="primary"
            @click="handleRetry(file)"
          >
            重试
          </el-link>
          <el-link
            v-if="!disabled"
            :underline="false"
            type="danger"
            @click="handleRemoveFailed(file.uid)"
          >
            删除
          </el-link>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import request from "@/utils/request";
import Sortable from "sortablejs";

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  // 上传接口必须返回fileId、originalFilename和downloadUrl
  action: {
    type: String,
    default: "/common/files/upload",
  },
  // 上传携带的额外参数
  data: {
    type: Object,
    default: () => ({}),
  },
  // 文件数量限制
  limit: {
    type: Number,
    default: 5,
  },
  // 文件大小限制(MB)
  fileSize: {
    type: Number,
    default: 5,
  },
  // 文件类型，例如["doc", "docx", "pdf"]
  fileType: {
    type: Array,
    default: () => ["doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "pdf"],
  },
  // 是否显示上传提示
  isShowTip: {
    type: Boolean,
    default: true,
  },
  // 禁用组件，仅保留文件下载
  disabled: {
    type: Boolean,
    default: false,
  },
  // 是否允许拖动排序
  drag: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(["update:modelValue", "change"]);
const { proxy } = getCurrentInstance();
const fileUploadRef = ref();
const uploadFileListRef = ref();
const fileList = ref([]);
const pendingFileList = ref([]);
let sortable;

const showTip = computed(
  () => props.isShowTip && (props.fileType.length > 0 || props.fileSize)
);

watch(
  () => props.modelValue,
  (value) => {
    fileList.value = normalizeFileList(value);
    nextTick(initSortable);
  },
  { deep: true, immediate: true }
);

/**
 * 校验待上传文件。
 *
 * @param {File} file 待上传文件
 * @returns {boolean} 是否允许上传
 */
function handleBeforeUpload(file) {
  if (fileList.value.length + uploadingCount() >= props.limit) {
    proxy.$modal.msgError(`上传文件数量不能超过 ${props.limit} 个`);
    return false;
  }
  const extension = getFileExtension(file.name);
  const allowedTypes = props.fileType.map((type) => String(type).toLowerCase());
  if (allowedTypes.length && !allowedTypes.includes(extension)) {
    proxy.$modal.msgError(
      `文件格式不正确，请上传 ${props.fileType.join("/")} 格式文件`
    );
    return false;
  }
  if (file.name.includes(",")) {
    proxy.$modal.msgError("文件名称不能包含英文逗号");
    return false;
  }
  if (props.fileSize && file.size / 1024 / 1024 > props.fileSize) {
    proxy.$modal.msgError(`上传文件大小不能超过 ${props.fileSize} MB`);
    return false;
  }
  pendingFileList.value.push({
    uid: file.uid,
    name: file.name,
    raw: file,
    status: "uploading",
    error: "",
  });
  return true;
}

/**
 * 使用项目请求封装上传文件。
 *
 * @param {Object} options Element Plus上传参数
 * @returns {Promise<Object>} 上传响应
 */
function handleUploadRequest(options) {
  return uploadFile(options.file, options.onProgress);
}

/**
 * 上传原始文件。
 *
 * @param {File} file 原始文件
 * @param {Function} onProgress 上传进度回调
 * @returns {Promise<Object>} 上传响应
 */
async function uploadFile(file, onProgress) {
  const formData = new FormData();
  formData.append("file", file);
  appendUploadData(formData);
  const response = await request({
    url: props.action,
    method: "post",
    data: formData,
    timeout: 120000,
    headers: {
      "Content-Type": "multipart/form-data",
      repeatSubmit: false,
    },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress({ percent: Math.round((event.loaded * 100) / event.total) });
      }
    },
  });
  if (!response.fileId || !response.downloadUrl) {
    throw new Error("上传响应缺少文件ID或下载地址");
  }
  return response;
}

/**
 * 追加上传接口的扩展参数。
 *
 * @param {FormData} formData 表单数据
 * @returns {void}
 */
function appendUploadData(formData) {
  Object.entries(props.data).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => formData.append(key, item));
      return;
    }
    formData.append(key, value);
  });
}

/**
 * 处理上传成功。
 *
 * @param {Object} response 上传响应
 * @param {Object} uploadFile Element Plus文件对象
 * @returns {void}
 */
function handleUploadSuccess(response, uploadFile) {
  pendingFileList.value = pendingFileList.value.filter(
    (item) => item.uid !== uploadFile.uid
  );
  const nextFile = {
    fileId: response.fileId,
    name: response.originalFilename || uploadFile.name,
    url: response.downloadUrl,
  };
  updateModel([
    ...fileList.value.filter((item) => item.fileId !== nextFile.fileId),
    nextFile,
  ]);
  clearInternalFiles();
}

/**
 * 处理上传失败。
 *
 * @param {Error} error 上传错误
 * @param {Object} uploadFile Element Plus文件对象
 * @returns {void}
 */
function handleUploadError(error, uploadFile) {
  const pendingFile = pendingFileList.value.find(
    (item) => item.uid === uploadFile.uid
  );
  if (pendingFile) {
    pendingFile.status = "failed";
    pendingFile.error = getErrorMessage(error);
  }
  clearInternalFiles();
}

/**
 * 重试失败文件。
 *
 * @param {Object} file 失败文件
 * @returns {Promise<void>}
 */
async function handleRetry(file) {
  file.status = "uploading";
  file.error = "";
  try {
    const response = await uploadFile(file.raw);
    handleUploadSuccess(response, file);
  } catch (error) {
    handleUploadError(error, file);
  }
}

/**
 * 下载受保护文件。
 *
 * @param {Object} file 文件信息
 * @returns {void}
 */
function handleDownload(file) {
  proxy.$download.file(file.url);
}

/**
 * 删除已上传文件。
 *
 * @param {string} fileId 文件ID
 * @returns {void}
 */
function handleDelete(fileId) {
  updateModel(fileList.value.filter((item) => item.fileId !== fileId));
}

/**
 * 移除上传失败文件。
 *
 * @param {string | number} uid 上传文件UID
 * @returns {void}
 */
function handleRemoveFailed(uid) {
  pendingFileList.value = pendingFileList.value.filter(
    (item) => item.uid !== uid
  );
}

/**
 * 更新结构化文件列表。
 *
 * @param {Array<Object>} value 文件列表
 * @returns {void}
 */
function updateModel(value) {
  const modelValue = value.map(toModelFile);
  fileList.value = normalizeFileList(modelValue);
  emit("update:modelValue", modelValue);
  emit(
    "change",
    modelValue,
    modelValue.map((item) => item.fileId)
  );
  nextTick(initSortable);
}

/**
 * 获取文件ID列表。
 *
 * @returns {Array<string>} 文件ID列表
 */
function getFileIds() {
  return fileList.value.map((item) => item.fileId);
}

/**
 * 初始化文件拖动排序。
 *
 * @returns {void}
 */
function initSortable() {
  if (sortable) {
    sortable.destroy();
    sortable = undefined;
  }
  if (!props.drag || props.disabled || !uploadFileListRef.value) {
    return;
  }
  sortable = Sortable.create(uploadFileListRef.value, {
    ghostClass: "business-file-drag",
    onEnd: (event) => {
      const nextList = [...fileList.value];
      const movedFile = nextList.splice(event.oldIndex, 1)[0];
      nextList.splice(event.newIndex, 0, movedFile);
      updateModel(nextList);
    },
  });
}

/**
 * 清理Element Plus内部文件，数量限制由结构化列表统一控制。
 *
 * @returns {void}
 */
function clearInternalFiles() {
  if (uploadingCount() === 0) {
    nextTick(() => fileUploadRef.value?.clearFiles());
  }
}

/**
 * 获取正在上传的文件数。
 *
 * @returns {number} 正在上传的文件数
 */
function uploadingCount() {
  return pendingFileList.value.filter((item) => item.status === "uploading")
    .length;
}

/**
 * 标准化外部传入的结构化文件列表。
 *
 * @param {Array<Object>} value 外部文件列表
 * @returns {Array<Object>} 标准化文件列表
 */
function normalizeFileList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => item && typeof item === "object" && item.fileId)
    .map((item) => ({
      fileId: item.fileId,
      name:
        item.name ||
        item.originalFilename ||
        getFileName(item.url || item.downloadUrl || ""),
      url: item.url || item.downloadUrl || item.fileName || "",
    }))
    .filter((item) => item.url);
}

/**
 * 转换为业务表单保存的数据结构。
 *
 * @param {Object} file 文件信息
 * @returns {Object} 业务文件信息
 */
function toModelFile(file) {
  return {
    fileId: file.fileId,
    name: file.name,
    url: file.url,
  };
}

/**
 * 获取文件扩展名。
 *
 * @param {string} filename 文件名称
 * @returns {string} 小写扩展名
 */
function getFileExtension(filename) {
  const index = filename.lastIndexOf(".");
  return index > -1 ? filename.slice(index + 1).toLowerCase() : "";
}

/**
 * 从路径获取文件名称。
 *
 * @param {string} value 文件路径
 * @returns {string} 文件名称
 */
function getFileName(value) {
  const path = value.split("?")[0];
  return decodeURIComponent(path.slice(path.lastIndexOf("/") + 1));
}

/**
 * 获取可展示的上传错误。
 *
 * @param {Error} error 上传错误
 * @returns {string} 错误信息
 */
function getErrorMessage(error) {
  return error?.message || "上传失败，请重试";
}

onMounted(() => nextTick(initSortable));

onBeforeUnmount(() => {
  sortable?.destroy();
});

defineExpose({ getFileIds });
</script>

<style scoped lang="scss">
.business-file-upload {
  width: 100%;
}

.upload-tip-emphasis {
  color: #f56c6c;
}

.business-file-list {
  margin: 8px 0 0;
  padding: 0;
}

.business-file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  transition: none !important;
}

.business-file-main {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.business-file-name {
  overflow: hidden;
  color: var(--el-text-color-regular);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.business-file-actions {
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  margin-left: 12px;
}

.business-file-drag {
  background: var(--el-color-primary-light-9);
  opacity: 0.6;
}
</style>
