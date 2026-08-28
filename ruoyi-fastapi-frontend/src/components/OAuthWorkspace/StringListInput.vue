<template>
  <div class="string-list-input">
    <div v-for="(_item, index) in localItems" :key="index" class="string-list-row">
      <el-input
        v-model="localItems[index]"
        :placeholder="placeholder"
        @blur="emitValue"
        @keyup.enter="appendAfter(index)"
      />
      <el-button
        text
        type="danger"
        icon="Delete"
        :aria-label="`删除第 ${index + 1} 项`"
        @click="remove(index)"
      />
    </div>
    <el-button class="add-row" text type="primary" icon="Plus" @click="append">
      {{ addText }}
    </el-button>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  addText: { type: String, default: '添加一项' }
})
const emit = defineEmits(['update:modelValue'])
const localItems = ref([])

function syncFromValue(value) {
  const items = Array.isArray(value) ? value.map(item => String(item ?? '')) : []
  localItems.value = items.length ? items : ['']
}

function emitValue() {
  emit('update:modelValue', localItems.value.map(item => item.trim()).filter(Boolean))
}

function append() {
  localItems.value.push('')
}

function appendAfter(index) {
  if (!localItems.value[index]?.trim()) return
  localItems.value.splice(index + 1, 0, '')
}

function remove(index) {
  localItems.value.splice(index, 1)
  if (!localItems.value.length) localItems.value.push('')
  emitValue()
}

watch(() => props.modelValue, syncFromValue, { immediate: true, deep: true })
</script>

<style scoped>
.string-list-input {
  width: 100%;
}

.string-list-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  gap: 6px;
  margin-bottom: 8px;
}

.string-list-row :deep(.el-button) {
  width: 36px;
  margin: 0;
}

.add-row {
  margin-left: 0;
}
</style>
