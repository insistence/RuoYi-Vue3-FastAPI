<template>
  <section class="file-statistics">
    <div class="file-statistics-header">
      <div>
        <div class="file-statistics-title">文件概览</div>
        <div class="file-statistics-tip">统计数据随当前查询条件实时更新</div>
      </div>
    </div>
    <div class="file-statistics-content">
      <div class="file-stat-item stat-primary">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">文件总数</div>
            <div class="file-stat-value">{{ stats.totalCount }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><Files /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>正常 {{ stats.activeCount }}</span>
          <span>回收站 {{ stats.deletedCount }}</span>
        </div>
      </div>

      <div class="file-stat-item stat-purple">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">占用空间</div>
            <div class="file-stat-value">{{ formatFileSize(stats.totalSize) }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><DataLine /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>全部文件累计占用</span>
        </div>
      </div>

      <div class="file-stat-item stat-green">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">公开文件空间</div>
            <div class="file-stat-value">{{ formatFileSize(stats.publicSize) }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><FolderOpened /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>占总空间 {{ formatPercentage(stats.publicSize) }}</span>
        </div>
      </div>

      <div class="file-stat-item stat-orange">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">受保护文件空间</div>
            <div class="file-stat-value">{{ formatFileSize(stats.privateSize) }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><Lock /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>占总空间 {{ formatPercentage(stats.privateSize) }}</span>
        </div>
      </div>

      <div class="file-stat-item stat-red">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">已过期文件</div>
            <div class="file-stat-value">{{ stats.expiredCount }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><Timer /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>7天内到期 {{ stats.retentionExpiringCount }}</span>
        </div>
      </div>

      <div class="file-stat-item stat-cyan">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">即将过期授权</div>
            <div class="file-stat-value">{{ stats.aclExpiringCount }}</div>
          </div>
          <div class="file-stat-icon"><el-icon><Key /></el-icon></div>
        </div>
        <div class="file-stat-extra">
          <span>7天内失效的 ACL 项</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import {
  DataLine,
  Files,
  FolderOpened,
  Key,
  Lock,
  Timer
} from "@element-plus/icons-vue";
import { formatFileSize } from "./fileFormatters";

const props = defineProps({
  stats: {
    type: Object,
    required: true
  }
});

function formatPercentage(size) {
  const totalSize = Number(props.stats.totalSize || 0);
  if (!totalSize) return "0%";
  const percentage = (Number(size || 0) / totalSize) * 100;
  return `${percentage >= 10 ? percentage.toFixed(0) : percentage.toFixed(1)}%`;
}
</script>

<style scoped>
.file-statistics {
  margin-bottom: 16px;
}

.file-statistics-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-left: 10px;
  border-left: 3px solid var(--el-color-primary);
}

.file-statistics-title {
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

.file-statistics-tip {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
}

.file-statistics-content {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.file-stat-item {
  --stat-color: var(--el-color-primary);
  position: relative;
  min-width: 0;
  min-height: 118px;
  padding: 16px;
  overflow: hidden;
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--stat-color) 9%, var(--el-bg-color)) 0%,
      var(--el-bg-color) 58%
    );
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  box-shadow: 0 4px 14px rgb(31 45 61 / 5%);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.file-stat-item::after {
  position: absolute;
  right: -22px;
  bottom: -28px;
  width: 78px;
  height: 78px;
  background-color: var(--stat-color);
  border-radius: 50%;
  opacity: 0.05;
  content: "";
}

.file-stat-item:hover {
  box-shadow: 0 8px 22px rgb(31 45 61 / 9%);
  transform: translateY(-2px);
}

.file-stat-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.file-stat-title {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 20px;
}

.file-stat-value {
  margin-top: 5px;
  color: var(--el-text-color-primary);
  font-size: 25px;
  font-weight: 650;
  line-height: 32px;
  white-space: nowrap;
}

.file-stat-icon {
  display: flex;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  color: var(--stat-color);
  font-size: 20px;
  background-color: color-mix(in srgb, var(--stat-color) 12%, transparent);
  border-radius: 10px;
}

.file-stat-extra {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.stat-purple {
  --stat-color: #7c5ce7;
}

.stat-green {
  --stat-color: #20a162;
}

.stat-orange {
  --stat-color: #e58a17;
}

.stat-red {
  --stat-color: #e45656;
}

.stat-cyan {
  --stat-color: #168d9c;
}

@media (max-width: 1280px) {
  .file-statistics-content {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .file-statistics-content {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .file-statistics-content {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
