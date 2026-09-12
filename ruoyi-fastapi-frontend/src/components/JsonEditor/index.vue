<template>
  <div class="json-editor" :class="{ 'has-error': !validation.valid }">
    <div class="json-editor__toolbar">
      <span class="json-editor__type">{{ valueType === 'array' ? 'JSON 数组 [ ]' : 'JSON 对象 { }' }}</span>
      <div class="json-editor__actions">
        <el-button link type="primary" icon="Operation" :disabled="!editorReady || !validation.valid"
          :aria-label="`格式化${label}`" @click="formatDocument">格式化</el-button>
        <el-button link icon="FullScreen" :aria-label="`${expanded ? '收起' : '展开'}${label}编辑器`"
          :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起' : '展开' }}</el-button>
      </div>
    </div>
    <div class="json-editor__body" :style="{ height: expanded ? '360px' : '160px' }">
      <div v-if="!loadFailed" ref="editorRef" class="json-editor__canvas" />
      <div v-if="!editorReady && !loadFailed" class="json-editor__loading" role="status">正在加载编辑器…</div>
      <el-input v-if="loadFailed" :model-value="modelValue" type="textarea" :rows="expanded ? 16 : 7"
        :aria-label="label" @update:model-value="updateValue" @blur="validateForm" />
    </div>
    <div class="json-editor__footer">
      <span v-if="validation.valid" class="json-editor__valid" role="status">格式正确</span>
      <button v-else type="button" class="json-editor__error" @click="revealError">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ errorLocation }}{{ validation.message }}</span>
      </button>
      <span v-if="validation.valid" class="json-editor__hint">{{ loadFailed ? '编辑器加载失败，已切换文本输入' : 'Tab 切换焦点 · Alt+Shift+F 格式化' }}</span>
    </div>
  </div>
</template>

<script setup name="JsonEditor">
import { useFormItem } from 'element-plus'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: 'JSON参数' },
  valueType: { type: String, default: 'object' },
  validate: { type: Function, default: (value) => JSON.parse(value) }
})
const emit = defineEmits(['update:modelValue'])
const { formItem } = useFormItem()
const editorRef = ref()
const editorReady = ref(false)
const loadFailed = ref(false)
const expanded = ref(false)
const firstMarker = shallowRef()
const validation = computed(() => {
  try {
    props.validate(props.modelValue)
    return { valid: true }
  } catch (error) {
    return { valid: false, message: error.message }
  }
})
const errorLocation = computed(() => firstMarker.value
  ? `第 ${firstMarker.value.startLineNumber} 行，第 ${firstMarker.value.startColumn} 列：`
  : '')

let editor
let model
let themeObserver
let disposed = false
const listeners = []

/** 同步输入内容，修正后及时清除表单错误 */
function updateValue(value) {
  emit('update:modelValue', value)
  if (formItem?.validateState === 'error') {
    nextTick(validateForm)
  }
}

/** 与所在表单共用字段校验 */
function validateForm() {
  formItem?.validate('blur').catch(() => {})
}

/** 格式化当前文档，保留编辑器撤销记录 */
async function formatDocument() {
  if (!editor || !validation.value.valid) return
  await editor.getAction('editor.action.formatDocument')?.run()
  editor.focus()
}

/** 定位JSON语法错误，容器类型错误定位到文档开头 */
function revealError() {
  const marker = firstMarker.value
  const position = { lineNumber: marker?.startLineNumber || 1, column: marker?.startColumn || 1 }
  editor?.setPosition(position)
  editor?.revealPositionInCenter(position)
  editor?.focus()
}

/** 跟随页面亮暗主题切换 */
function updateTheme() {
  editor?.updateOptions({ theme: document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs' })
}

watch(() => props.modelValue, (value) => {
  if (model && model.getValue() !== value) {
    model.setValue(value)
  }
})

onMounted(async () => {
  try {
    const [monaco] = await Promise.all([
      import('monaco-editor/esm/vs/editor/editor.api'),
      import('monaco-editor/esm/vs/language/json/monaco.contribution')
    ])
    if (disposed) return
    model = monaco.editor.createModel(props.modelValue, 'json')
    model.updateOptions({ tabSize: 2, insertSpaces: true })
    editor = monaco.editor.create(editorRef.value, {
      model,
      ariaLabel: props.label,
      automaticLayout: true,
      fontSize: 13,
      lineHeight: 22,
      lineNumbersMinChars: 3,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      folding: true,
      tabFocusMode: true,
      padding: { top: 8, bottom: 8 },
      stickyScroll: { enabled: false },
      formatOnPaste: true,
      suggest: { showWords: false },
      scrollbar: { alwaysConsumeMouseWheel: false }
    })
    listeners.push(editor.onDidChangeModelContent(() => updateValue(model.getValue())))
    listeners.push(editor.onDidBlurEditorText(validateForm))
    listeners.push(monaco.editor.onDidChangeMarkers((resources) => {
      if (resources.some(resource => resource.toString() === model.uri.toString())) {
        firstMarker.value = monaco.editor.getModelMarkers({ resource: model.uri })
          .filter(marker => marker.severity === monaco.MarkerSeverity.Error)
          .sort((left, right) => left.startLineNumber - right.startLineNumber || left.startColumn - right.startColumn)[0]
      }
    }))
    updateTheme()
    themeObserver = new MutationObserver(updateTheme)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    editorReady.value = true
  } catch {
    if (!disposed) loadFailed.value = true
  }
})

onBeforeUnmount(() => {
  disposed = true
  themeObserver?.disconnect()
  listeners.forEach(listener => listener.dispose())
  editor?.dispose()
  model?.dispose()
})
</script>

<style scoped>
.json-editor {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  line-height: 1.5;
}
.json-editor:focus-within {
  border-color: var(--el-color-primary);
}
.json-editor.has-error {
  border-color: var(--el-color-danger);
}
.json-editor__toolbar,
.json-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 6px 10px;
  background: var(--el-fill-color-light);
}
.json-editor__toolbar {
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.json-editor__type {
  color: var(--el-text-color-regular);
  font-family: var(--el-font-family);
  font-size: 12px;
}
.json-editor__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.json-editor__actions .el-button + .el-button {
  margin-left: 0;
}
.json-editor__body {
  position: relative;
}
.json-editor__canvas {
  width: 100%;
  height: 100%;
}
.json-editor__loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--el-text-color-secondary);
}
.json-editor__footer {
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
}
.json-editor__valid {
  color: var(--el-color-success);
}
.json-editor__hint {
  color: var(--el-text-color-secondary);
}
.json-editor__error {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--el-color-danger);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.json-editor__error:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
</style>
