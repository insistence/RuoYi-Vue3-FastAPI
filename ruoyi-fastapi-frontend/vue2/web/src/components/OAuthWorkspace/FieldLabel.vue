<template>
  <span class="field-label">
    <span>{{ label }}</span>
    <el-tooltip
      :content="help"
      placement="top"
      :open-delay="250"
    >
      <i
        class="field-help el-icon-question"
        tabindex="0"
        :aria-label="`${label}说明`"
        @click.stop
      ></i>
    </el-tooltip>
  </span>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  help: { type: String, required: true },
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
  color: var(--oauth-text-color-secondary);
  cursor: help;
  outline: none;
}

.field-help:hover,
.field-help:focus-visible {
  color: var(--oauth-color-primary);
}

.field-help:focus-visible {
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--oauth-color-primary-light-7);
}
</style>
