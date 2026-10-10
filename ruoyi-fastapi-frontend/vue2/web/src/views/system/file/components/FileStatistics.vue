<template>
  <section class="file-statistics">
    <div class="file-statistics-header">
      <div class="file-statistics-title">文件概览</div>
      <div class="file-statistics-tip">统计数据随当前查询条件实时更新</div>
    </div>
    <div class="file-statistics-content">
      <div class="file-stat-item stat-primary">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">文件总数</div>
            <div class="file-stat-value">{{ stats.totalCount }}</div>
          </div>
          <div class="file-stat-icon"><i class="el-icon-files" /></div>
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
          <div class="file-stat-icon"><i class="el-icon-data-line" /></div>
        </div>
        <div class="file-stat-extra"><span>全部文件累计占用</span></div>
      </div>

      <div class="file-stat-item stat-green">
        <div class="file-stat-main">
          <div>
            <div class="file-stat-title">公开文件空间</div>
            <div class="file-stat-value">{{ formatFileSize(stats.publicSize) }}</div>
          </div>
          <div class="file-stat-icon"><i class="el-icon-folder-opened" /></div>
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
          <div class="file-stat-icon"><i class="el-icon-lock" /></div>
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
          <div class="file-stat-icon"><i class="el-icon-timer" /></div>
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
          <div class="file-stat-icon"><i class="el-icon-key" /></div>
        </div>
        <div class="file-stat-extra"><span>7天内失效的 ACL 项</span></div>
      </div>
    </div>
  </section>
</template>

<script>
import { formatFileSize } from './fileFormatters'

export default {
  name: 'FileStatistics',
  props: {
    stats: {
      type: Object,
      required: true,
    },
  },
  methods: {
    formatFileSize,
    formatPercentage(size) {
      const totalSize = Number(this.stats.totalSize || 0)
      if (!totalSize) {
        return '0%'
      }
      const percentage = (Number(size || 0) / totalSize) * 100
      return `${percentage >= 10 ? percentage.toFixed(0) : percentage.toFixed(1)}%`
    },
  },
}
</script>

<style scoped>
.file-statistics {
  margin-bottom: 16px;
}

.file-statistics-header {
  margin-bottom: 14px;
  padding-left: 10px;
  border-left: 3px solid #409eff;
}

.file-statistics-title {
  color: #303133;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

.file-statistics-tip {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
  line-height: 18px;
}

.file-statistics-content {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 14px;
}

.file-stat-item {
  position: relative;
  min-width: 0;
  min-height: 118px;
  padding: 16px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  box-shadow: 0 4px 14px rgba(31, 45, 61, 0.05);
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
  background-color: currentColor;
  border-radius: 50%;
  opacity: 0.04;
  content: '';
}

.file-stat-item:hover {
  box-shadow: 0 8px 22px rgba(31, 45, 61, 0.09);
  transform: translateY(-2px);
}

.file-stat-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.file-stat-title {
  color: #909399;
  font-size: 13px;
  line-height: 20px;
}

.file-stat-value {
  margin-top: 5px;
  color: #303133;
  font-size: 25px;
  font-weight: 600;
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
  font-size: 20px;
  border-radius: 10px;
}

.file-stat-extra {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  color: #909399;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.stat-primary {
  color: #409eff;
}

.stat-primary .file-stat-icon {
  background: #ecf5ff;
}

.stat-purple {
  color: #7c5ce7;
}

.stat-purple .file-stat-icon {
  background: #f1edfd;
}

.stat-green {
  color: #20a162;
}

.stat-green .file-stat-icon {
  background: #e9f7f0;
}

.stat-orange {
  color: #e58a17;
}

.stat-orange .file-stat-icon {
  background: #fdf3e7;
}

.stat-red {
  color: #e45656;
}

.stat-red .file-stat-icon {
  background: #fdf0f0;
}

.stat-cyan {
  color: #168d9c;
}

.stat-cyan .file-stat-icon {
  background: #e8f5f7;
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
