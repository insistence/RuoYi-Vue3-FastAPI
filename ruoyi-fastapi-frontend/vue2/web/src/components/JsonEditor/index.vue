<template>
  <div
    class="json-editor"
    :class="{ 'has-error': !validation.valid }"
  >
    <div class="json-editor__toolbar">
      <span class="json-editor__type">{{
        valueType === 'array' ? 'JSON 数组 [ ]' : 'JSON 对象 { }'
      }}</span>
      <div class="json-editor__actions">
        <el-button
          type="text"
          size="mini"
          icon="el-icon-s-operation"
          :disabled="!editorReady || !validation.valid"
          :aria-label="`格式化${label}`"
          @click="formatDocument"
          >格式化</el-button
        >
        <el-button
          type="text"
          size="mini"
          icon="el-icon-full-screen"
          :aria-label="`${expanded ? '收起' : '展开'}${label}编辑器`"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
          >{{ expanded ? '收起' : '展开' }}</el-button
        >
      </div>
    </div>
    <div
      class="json-editor__body"
      :style="{ height: expanded ? '360px' : '100px' }"
    >
      <div
        v-if="!loadFailed"
        ref="editorRef"
        class="json-editor__canvas"
      />
      <div
        v-if="!editorReady && !loadFailed"
        class="json-editor__loading"
        role="status"
      >
        正在加载编辑器…
      </div>
      <el-input
        v-if="loadFailed"
        :value="value"
        type="textarea"
        :rows="expanded ? 16 : 4"
        :aria-label="label"
        @input="updateValue"
        @blur="validateForm"
      />
    </div>
    <div class="json-editor__footer">
      <span
        v-if="validation.valid"
        class="json-editor__valid"
        role="status"
        >格式正确</span
      >
      <button
        v-else
        type="button"
        class="json-editor__error"
        @click="revealError"
      >
        <i
          class="el-icon-warning"
          aria-hidden="true"
        ></i>
        <span>{{ errorLocation }}{{ validation.message }}</span>
      </button>
      <span
        v-if="validation.valid"
        class="json-editor__hint"
        >{{
          loadFailed ? '编辑器加载失败，已切换文本输入' : 'Tab 切换焦点 · Alt+Shift+F 格式化'
        }}</span
      >
    </div>
  </div>
</template>

<script>
import { loadMonaco } from '@/utils/monaco'
export default {
  name: 'JsonEditor',
  props: {
    value: {
      type: String,
      default: '',
    },
    label: {
      type: String,
      default: 'JSON参数',
    },
    valueType: {
      type: String,
      default: 'object',
    },
    validate: {
      type: Function,
      default: (value) => JSON.parse(value),
    },
  },
  inject: {
    formItem: {
      from: 'elFormItem',
      default: null,
    },
  },
  data() {
    return {
      editorReady: false,
      loadFailed: false,
      expanded: false,
      firstMarker: undefined,
    }
  },
  computed: {
    validation() {
      try {
        this.validate(this.value)
        return {
          valid: true,
        }
      } catch (error) {
        return {
          valid: false,
          message: error.message,
        }
      }
    },
    errorLocation() {
      return this.firstMarker
        ? `第 ${this.firstMarker.startLineNumber} 行，第 ${this.firstMarker.startColumn} 列：`
        : ''
    },
  },
  watch: {
    value(value) {
      if (this._model && this._model.getValue() !== value) {
        this._model.setValue(value)
      }
    },
  },
  beforeCreate() {
    this._editor = undefined
    this._model = undefined
    this._themeObserver = undefined
    this._disposed = false
    this._listeners = []
  },
  async mounted() {
    try {
      const monaco = await loadMonaco()
      if (this._disposed) return
      this._model = monaco.editor.createModel(this.value, 'json')
      this._model.updateOptions({
        tabSize: 2,
        insertSpaces: true,
      })
      this._editor = monaco.editor.create(this.$refs.editorRef, {
        model: this._model,
        ariaLabel: this.label,
        automaticLayout: true,
        fontSize: 13,
        lineHeight: 22,
        lineNumbersMinChars: 3,
        minimap: {
          enabled: false,
        },
        scrollBeyondLastLine: false,
        wordWrap: 'on',
        folding: true,
        tabFocusMode: true,
        padding: {
          top: 8,
          bottom: 8,
        },
        stickyScroll: {
          enabled: false,
        },
        formatOnPaste: true,
        suggest: {
          showWords: false,
        },
        scrollbar: {
          alwaysConsumeMouseWheel: false,
        },
      })
      this._listeners.push(
        this._editor.onDidChangeModelContent(() => this.updateValue(this._model.getValue()))
      )
      this._listeners.push(this._editor.onDidBlurEditorText(this.validateForm))
      this._listeners.push(
        monaco.editor.onDidChangeMarkers((resources) => {
          if (resources.some((resource) => resource.toString() === this._model.uri.toString())) {
            this.firstMarker = monaco.editor
              .getModelMarkers({
                resource: this._model.uri,
              })
              .filter((marker) => marker.severity === monaco.MarkerSeverity.Error)
              .sort(
                (left, right) =>
                  left.startLineNumber - right.startLineNumber ||
                  left.startColumn - right.startColumn
              )[0]
          }
        })
      )
      this.updateTheme()
      this._themeObserver = new MutationObserver(this.updateTheme)
      this._themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class'],
      })
      this.editorReady = true
    } catch {
      if (!this._disposed) this.loadFailed = true
    }
  },
  beforeDestroy() {
    this._disposed = true
    this._themeObserver?.disconnect()
    this._listeners.forEach((listener) => listener.dispose())
    this._editor?.dispose()
    this._model?.dispose()
  },
  methods: {
    /** 同步输入内容，修正后及时清除表单错误 */
    updateValue(value) {
      this.$emit('input', value)
      if (this.formItem?.validateState === 'error') {
        this.$nextTick(this.validateForm)
      }
    },
    /** 与所在表单共用字段校验 */
    validateForm() {
      if (this.formItem) this.formItem.validate('blur', () => {})
    },
    /** 格式化当前文档，保留编辑器撤销记录 */
    async formatDocument() {
      if (!this._editor || !this.validation.valid) return
      await this._editor.getAction('editor.action.formatDocument')?.run()
      this._editor.focus()
    },
    /** 定位JSON语法错误，容器类型错误定位到文档开头 */
    revealError() {
      const marker = this.firstMarker
      const position = {
        lineNumber: marker?.startLineNumber || 1,
        column: marker?.startColumn || 1,
      }
      this._editor?.setPosition(position)
      this._editor?.revealPositionInCenter(position)
      this._editor?.focus()
    },
    /** 跟随页面亮暗主题切换 */
    updateTheme() {
      this._editor?.updateOptions({
        theme: document.documentElement.classList.contains('dark') ? 'vs-dark' : 'vs',
      })
    },
  },
}
</script>

<style scoped>
.json-editor {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  line-height: 1.5;
}
.json-editor:focus-within {
  border-color: #409eff;
}
.json-editor.has-error {
  border-color: #f56c6c;
}
.json-editor__toolbar,
.json-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 6px 10px;
  background: #f5f7fa;
}
.json-editor__toolbar {
  border-bottom: 1px solid #ebeef5;
}
.json-editor__type {
  color: #606266;
  font-family: inherit;
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
  color: #909399;
}
.json-editor__footer {
  border-top: 1px solid #ebeef5;
  font-size: 12px;
}
.json-editor__valid {
  color: #67c23a;
}
.json-editor__hint {
  color: #909399;
}
.json-editor__error {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #f56c6c;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.json-editor__error:focus-visible {
  outline: 2px solid #409eff;
  outline-offset: 2px;
}
</style>
