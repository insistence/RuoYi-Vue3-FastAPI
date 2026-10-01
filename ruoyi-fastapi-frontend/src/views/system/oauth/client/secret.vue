<template>
  <el-dialog
    v-model="visible"
    title="保存应用密钥"
    width="min(680px, calc(100vw - 48px))"
    append-to-body
    :close-on-click-modal="false"
  >
    <el-form
      label-width="160px"
      class="secret-form"
    >
      <el-form-item>
        <template #label
          ><FieldLabel
            label="应用编号"
            help="系统生成的应用编号，复制后用于配置外部应用。"
        /></template>
        <el-input
          :model-value="secret.clientId"
          readonly
        />
      </el-form-item>
      <el-form-item>
        <template #label
          ><FieldLabel
            label="应用密钥"
            help="应用密钥相当于应用密码，只显示这一次；请复制后保存在安全的密钥管理系统中。"
        /></template>
        <el-input
          :model-value="secret.clientSecret"
          readonly
        >
          <template #append>
            <el-button
              icon="CopyDocument"
              @click="copySecret"
              >复制</el-button
            >
          </template>
        </el-input>
      </el-form-item>
    </el-form>
    <el-checkbox v-model="confirmed">我已将密钥保存到安全位置</el-checkbox>
    <template #footer>
      <el-button
        type="primary"
        :disabled="!confirmed"
        @click="close"
        >完成</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup>
import FieldLabel from '@/components/OAuthWorkspace/FieldLabel.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  secret: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])
const { proxy } = getCurrentInstance()
const confirmed = ref(false)
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      confirmed.value = false
    }
  }
)

/** 复制本次生成的客户端密钥 */
async function copySecret() {
  if (!props.secret.clientSecret) {
    return
  }
  try {
    await navigator.clipboard.writeText(props.secret.clientSecret)
    proxy.$modal.msgSuccess('密钥已复制')
  } catch {
    proxy.$modal.msgError('浏览器拒绝访问剪贴板，请手动复制')
  }
}

/** 关闭密钥展示对话框 */
function close() {
  visible.value = false
}
</script>

<style scoped>
@media (max-width: 640px) {
  .secret-form :deep(.el-form-item) {
    display: block;
  }

  .secret-form :deep(.el-form-item__label) {
    width: auto !important;
    margin-bottom: 6px;
  }

  .secret-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }
}
</style>
