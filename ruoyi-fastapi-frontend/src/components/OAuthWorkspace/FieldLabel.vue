<template>
  <span class="field-label">
    <span>{{ label }}</span>
    <el-tooltip :content="help" placement="top" :show-after="250">
      <el-icon
        class="field-help"
        tabindex="0"
        :aria-label="`${label}说明`"
        @click.stop
      >
        <question-filled />
      </el-icon>
    </el-tooltip>
  </span>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  help: { type: String, required: true }
})
</script>

<style scoped>
.field-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.field-help {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  cursor: help;
  outline: none;
}

.field-help:hover,
.field-help:focus-visible {
  color: var(--el-color-primary);
}

.field-help:focus-visible {
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}
</style>
