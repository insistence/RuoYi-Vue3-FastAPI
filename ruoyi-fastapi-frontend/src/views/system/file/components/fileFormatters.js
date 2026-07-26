import { parseTime } from "@/utils/ruoyi";

export function formatFileSize(size) {
  const bytes = Number(size || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function accessTypeLabel(accessType) {
  return accessType === "public" ? "公开文件" : "受保护文件";
}

export function statusLabel(status) {
  return {
    active: "正常",
    deleted: "已删除",
    purging: "清理中"
  }[status] || status;
}

export function expirationLabel(expireTime) {
  if (!expireTime) return "永久有效";
  const remainingTime = new Date(expireTime).getTime() - Date.now();
  if (remainingTime <= 0) return "已过期";
  if (remainingTime <= 7 * 24 * 60 * 60 * 1000) return "即将过期";
  return parseTime(expireTime, "{y}-{m}-{d}");
}

export function expirationTagType(expireTime) {
  if (!expireTime) return "info";
  const remainingTime = new Date(expireTime).getTime() - Date.now();
  if (remainingTime <= 0) return "danger";
  return remainingTime <= 7 * 24 * 60 * 60 * 1000 ? "warning" : "success";
}

export function isAclExpiring(expireTime) {
  if (!expireTime) return false;
  const remainingTime = new Date(expireTime).getTime() - Date.now();
  return remainingTime > 0 && remainingTime <= 7 * 24 * 60 * 60 * 1000;
}

export function storageStatusLabel(storageStatus) {
  return {
    normal: "正常",
    missing: "文件缺失",
    quarantined: "已隔离",
    invalid: "异常"
  }[storageStatus] || "未知";
}

export function storageStatusTagType(storageStatus) {
  return {
    normal: "success",
    missing: "danger",
    quarantined: "warning",
    invalid: "danger"
  }[storageStatus] || "info";
}

export function actionLabel(action) {
  return {
    upload: "上传",
    download: "下载",
    acl_update: "授权变更",
    transfer: "归属转移",
    delete: "移入回收站",
    restore: "恢复",
    purge: "永久清理",
    reconcile: "存储对账",
    retention_extend: "保留延期",
    retention_dispose: "到期处置"
  }[action] || action;
}

export function resultLabel(result) {
  return {
    allowed: "已授权",
    denied: "已拒绝",
    completed: "已完成",
    failed: "失败"
  }[result] || result;
}

export function resultTagType(result) {
  return {
    allowed: "primary",
    denied: "danger",
    completed: "success",
    failed: "danger"
  }[result] || "info";
}

export function parseOperationDetail(operationDetail) {
  if (!operationDetail) return [];
  try {
    const detail = JSON.parse(operationDetail);
    return Object.entries(detail).map(([key, value]) => ({
      label: auditDetailKeyLabel(key),
      value: typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "-")
    }));
  } catch {
    return [{ label: "操作详情", value: operationDetail }];
  }
}

function auditDetailKeyLabel(key) {
  return {
    previousAclVersion: "原权限版本",
    newAclVersion: "新权限版本",
    entryCount: "授权项数量",
    allowCount: "允许项数量",
    denyCount: "拒绝项数量",
    subjectTypeCounts: "主体类型统计",
    previousOwnerUserId: "原所有者ID",
    previousDeptId: "原所属部门ID",
    newOwnerUserId: "新所有者ID",
    newOwnerName: "新所有者",
    newDeptId: "新所属部门ID",
    reason: "操作原因",
    originalName: "原始文件名",
    accessType: "访问类型",
    referenceCount: "业务引用数量",
    previousStatus: "原状态",
    newStatus: "新状态",
    truncated: "详情已截断",
    preview: "详情预览",
    issueId: "对账异常ID",
    issueType: "异常类型",
    action: "处理动作",
    actualRoot: "实际存储区域",
    actualKey: "实际相对路径",
    expectedRoot: "预期存储区域",
    expectedKey: "预期相对路径",
    previousExpireTime: "原到期时间",
    newExpireTime: "新到期时间",
    expireTime: "到期时间",
    range: "请求范围",
    rangeStart: "分段起始字节",
    rangeEnd: "分段结束字节",
    fileSize: "文件总大小",
    releasedReferenceCount: "解除引用数量",
    releasedReferences: "解除引用明细"
  }[key] || key;
}
