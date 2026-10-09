<template>
  <div class="plugin-release-status">
    <el-tag :type="view.tagType">{{ view.label }}</el-tag>
    <span class="plugin-release-workers">{{ view.workerSummary }}</span>
  </div>
</template>

<script setup name="PluginReleaseStatus">
import { computed } from 'vue'
import { getPluginReleaseView } from '@/utils/pluginReleaseFormatter'

const props = defineProps({
  plugin: {
    type: Object,
    required: true,
  },
})
const view = computed(() => getPluginReleaseView(props.plugin))
</script>

<style scoped>
.plugin-release-status {
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 4px;
}

.plugin-release-workers {
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.5;
}
</style>
