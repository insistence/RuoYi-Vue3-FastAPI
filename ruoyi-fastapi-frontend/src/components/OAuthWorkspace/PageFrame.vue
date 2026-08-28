<template>
  <div class="app-container oauth-workspace">
    <header class="workspace-header">
      <div class="workspace-heading">
        <h2>{{ title }}</h2>
        <span class="workspace-section">{{ section }}</span>
        <p>{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="workspace-actions">
        <slot name="actions" />
      </div>
    </header>

    <section v-if="$slots.context" class="workspace-context" aria-label="页面概览">
      <slot name="context" />
    </section>

    <section v-if="$slots.filters" class="workspace-filters" aria-label="筛选条件">
      <div class="filter-heading">
        <div>
          <span class="filter-title">筛选条件</span>
          <span v-if="filterHint" class="filter-hint">{{ filterHint }}</span>
        </div>
        <slot name="filter-extra" />
      </div>
      <slot name="filters" />
    </section>

    <section class="workspace-data">
      <div v-if="$slots.toolbar" class="data-toolbar">
        <slot name="toolbar" />
      </div>
      <slot />
    </section>
  </div>
</template>

<script setup>
defineProps({
  section: { type: String, default: '统一认证' },
  title: { type: String, required: true },
  description: { type: String, required: true },
  filterHint: { type: String, default: '' }
})
</script>

<style scoped>
.oauth-workspace {
  --workspace-surface: var(--el-bg-color-overlay);
  --workspace-border: var(--el-border-color-lighter);
  min-height: calc(100vh - 84px);
  background: transparent;
}

.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 0 12px;
}

.workspace-heading {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.workspace-section {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  height: 18px;
  padding-left: 12px;
  color: var(--el-color-primary);
  border-left: 1px solid var(--el-border-color);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
}

.workspace-heading h2 {
  flex: 0 0 auto;
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 20px;
  font-weight: 650;
  line-height: 30px;
}

.workspace-heading p {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  padding-top: 0;
}

.workspace-context,
.workspace-filters,
.workspace-data {
  margin-bottom: 16px;
  background: var(--workspace-surface);
  border: 1px solid var(--workspace-border);
  border-radius: 10px;
}

.workspace-context {
  padding: 18px 20px;
}

.workspace-filters {
  padding: 16px 18px 4px;
}

.filter-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  margin-bottom: 14px;
}

.filter-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 600;
}

.filter-hint {
  margin-left: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.workspace-filters :deep(.el-form-item) {
  margin-bottom: 14px;
}

.workspace-data {
  overflow: hidden;
}

.data-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  padding: 0 16px;
  border-bottom: 1px solid var(--workspace-border);
}

.workspace-data :deep(.el-table) {
  --el-table-header-bg-color: var(--el-fill-color-light);
}

.workspace-data :deep(.el-table th.el-table__cell) {
  height: 46px;
  color: var(--el-text-color-regular);
  font-weight: 600;
}

.workspace-data :deep(.el-table td.el-table__cell) {
  height: 58px;
}

.workspace-data :deep(.table-actions) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  white-space: nowrap;
}

.workspace-data :deep(.table-actions .el-button + .el-button) {
  margin-left: 0;
}

.workspace-data :deep(.table-actions .el-dropdown) {
  flex: 0 0 auto;
}

.workspace-data :deep(.pagination-container) {
  margin: 0;
  padding: 15px 16px;
  background: transparent;
  border-top: 1px solid var(--workspace-border);
}

@media (max-width: 768px) {
  .oauth-workspace {
    min-height: 100%;
  }

  .workspace-header {
    display: block;
  }

  .workspace-heading {
    flex-wrap: wrap;
    gap: 4px 10px;
  }

  .workspace-heading p {
    flex-basis: 100%;
    overflow: visible;
    white-space: normal;
  }

  .workspace-actions {
    padding-top: 10px;
  }

  .workspace-filters {
    overflow-x: auto;
  }
}

@media (prefers-reduced-motion: reduce) {

  .oauth-workspace *,
  .oauth-workspace *::before,
  .oauth-workspace *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
