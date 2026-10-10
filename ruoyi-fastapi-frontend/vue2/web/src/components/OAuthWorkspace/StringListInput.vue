<template>
  <div class="string-list-input">
    <div
      v-for="(_item, index) in localItems"
      :key="index"
      class="string-list-row"
    >
      <el-input
        v-model="localItems[index]"
        :placeholder="placeholder"
        @blur="emitValue"
        @keyup.enter.native="appendAfter(index)"
      />
      <el-button
        class="oauth-button-danger"
        type="text"
        icon="el-icon-delete"
        :aria-label="`删除第 ${index + 1} 项`"
        @click="remove(index)"
      />
    </div>
    <el-button
      type="text"
      class="add-row"
      icon="el-icon-plus"
      @click="append"
    >
      {{ addText }}
    </el-button>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
const props = defineProps({
  value: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  addText: { type: String, default: '添加一项' },
})
const emit = defineEmits(['input'])
const localItems = ref([])

/** 同步外部列表，空列表保留一个输入行 */
function syncFromValue(value) {
  const items = Array.isArray(value) ? value.map((item) => String(item ?? '')) : []
  localItems.value = items.length ? items : ['']
}

/** 过滤空值并更新列表绑定 */
function emitValue() {
  emit('input', localItems.value.map((item) => item.trim()).filter(Boolean))
}

/** 新增输入行 */
function append() {
  localItems.value.push('')
}

/** 在当前非空输入行后插入一行 */
function appendAfter(index) {
  if (!localItems.value[index]?.trim()) {
    return
  }
  localItems.value.splice(index + 1, 0, '')
}

/** 删除输入行并更新列表绑定 */
function remove(index) {
  localItems.value.splice(index, 1)
  if (!localItems.value.length) {
    localItems.value.push('')
  }
  emitValue()
}

watch(() => props.value, syncFromValue, { immediate: true, deep: true })
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
