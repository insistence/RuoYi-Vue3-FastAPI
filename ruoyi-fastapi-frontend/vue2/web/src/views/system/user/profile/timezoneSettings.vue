<template>
  <el-form
    label-width="100px"
    @submit.native.prevent="save"
  >
    <el-form-item label="时间显示方式">
      <el-radio-group
        v-model="mode"
        :disabled="saving"
      >
        <el-radio label="auto">自动跟随设备</el-radio>
        <el-radio label="custom">手动选择</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item
      v-if="mode === 'custom'"
      label="显示时区"
      :error="fieldError"
    >
      <el-select
        v-model="selectedZone"
        filterable
        :disabled="saving"
        :loading="loading"
        placeholder="搜索时区，例如 Asia/Shanghai"
        aria-label="显示时区"
        style="width: 100%"
        @change="fieldError = ''"
      >
        <el-option
          v-for="zone in timezones"
          :key="zone"
          :label="zone"
          :value="zone"
        />
      </el-select>
    </el-form-item>
    <el-form-item v-if="loadError">
      <el-alert
        type="warning"
        :closable="false"
      >
        <span slot="title">
          时区列表加载失败，仍可使用当前时区。
          <el-button
            type="text"
            size="mini"
            :loading="loading"
            @click="loadOptions"
            >重试</el-button
          >
        </span>
      </el-alert>
    </el-form-item>
    <el-form-item label="预览时区">
      <span>{{ previewZone }}</span>
    </el-form-item>
    <el-form-item label="时间预览">
      <span aria-live="polite">{{ previewTime }}</span>
      <div
        v-if="mode === 'auto' && !deviceZone"
        class="timezone-help"
      >
        当前设备无法识别时区，已使用系统时区；你也可以手动选择。
      </div>
      <div class="timezone-help">
        用于时间显示、日期筛选和导出。定时任务和业务统计使用各自配置的时区。
      </div>
    </el-form-item>
    <el-form-item :error="saveError">
      <el-button
        type="primary"
        size="mini"
        native-type="submit"
        :loading="saving"
        >保存</el-button
      >
      <el-button
        type="danger"
        size="mini"
        @click="close"
        >关闭</el-button
      >
    </el-form-item>
  </el-form>
</template>

<script>
import { getTimezoneOptions, updateUserTimezone } from '@/api/system/user'
import {
  formatBusinessTime,
  getBusinessTimezone,
  getDeviceTimezone,
  getDisplayTimezone,
  getSupportedTimezones,
} from '@/utils/time'
export default {
  name: 'TimezoneSettings',
  props: {
    user: Object,
  },
  data() {
    return {
      mode: this.$store.state.user.timeZone === 'auto' ? 'auto' : 'custom',
      selectedZone: getDisplayTimezone(),
      timezones: getSupportedTimezones(),
      loading: false,
      loadError: false,
      saving: false,
      saveError: '',
      fieldError: '',
      now: new Date(),
    }
  },
  computed: {
    deviceZone() {
      return getDeviceTimezone()
    },
    previewZone() {
      return this.mode === 'auto' ? this.deviceZone || getBusinessTimezone() : this.selectedZone
    },
    previewTime() {
      return formatBusinessTime(this.now, 'YYYY-MM-DD HH:mm:ss', this.previewZone)
    },
    userTimezone() {
      return this.user?.timeZone
    },
  },
  watch: {
    userTimezone(value) {
      if (!value) {
        return
      }
      this.mode = value === 'auto' ? 'auto' : 'custom'
      this.selectedZone = value === 'auto' ? getDisplayTimezone() : value
    },
  },
  mounted() {
    this.loadOptions()
  },
  methods: {
    close() {
      this.$tab.closePage()
    },
    /** 加载当前浏览器支持的时区选项。 */
    async loadOptions() {
      this.loading = true
      this.loadError = false
      try {
        const response = await getTimezoneOptions()
        this.timezones = getSupportedTimezones(response.data)
      } catch {
        this.loadError = true
      } finally {
        this.loading = false
      }
    },
    /** 保存账号时区，并同步当前页面展示。 */
    async save() {
      if (this.saving) {
        return
      }
      if (this.mode === 'custom' && !this.selectedZone) {
        this.fieldError = '请选择显示时区'
        return
      }
      this.saving = true
      this.saveError = ''
      const preference = this.mode === 'auto' ? 'auto' : this.selectedZone
      try {
        await updateUserTimezone(preference)
        this.$store.dispatch('ApplyTimezone', preference)
        this.$emit('saved', preference)
        this.now = new Date()
        this.$modal.msgSuccess('时区设置已保存')
      } catch (error) {
        this.saveError = error.message || '保存失败，请重试'
      } finally {
        this.saving = false
      }
    },
  },
}
</script>

<style scoped>
.timezone-help {
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
</style>
