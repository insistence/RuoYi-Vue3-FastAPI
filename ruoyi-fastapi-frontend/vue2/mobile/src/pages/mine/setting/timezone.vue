<template>
  <view class="flex h-full flex-col overflow-y-auto bg-white p-4">
    <view class="space-y-5">
      <!-- 跟随设备 -->
      <label class="flex min-h-11 items-center justify-between gap-4">
        <text class="text-sm font-medium text-gray-700">自动跟随设备</text>
        <switch
          :checked="followDevice"
          :disabled="saving || initializing"
          color="#3b82f6"
          aria-label="自动跟随设备"
          @change="followDevice = $event.detail.value"
        />
      </label>
      <!-- 显示时区 -->
      <view v-if="!followDevice" class="group relative">
        <label
          for="timezone-search"
          class="mb-2 block text-sm font-medium text-gray-700"
          >显示时区</label
        >
        <input
          id="timezone-search"
          v-model="zoneSearch"
          :disabled="saving || initializing"
          class="mb-3 h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          placeholder="搜索时区，例如 Asia/Shanghai"
          aria-label="搜索时区"
        />
        <picker
          :range="filteredTimezones"
          :value="selectedIndex"
          :disabled="
            saving || initializing || loading || !filteredTimezones.length
          "
          @change="selectTimezone"
        >
          <button
            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl bg-gray-50 px-4 py-2.5 text-left leading-normal ring-1 ring-gray-200 transition-all active:bg-gray-100"
            :disabled="
              saving || initializing || loading || !filteredTimezones.length
            "
            aria-label="选择显示时区"
          >
            <text class="break-all text-sm text-gray-800">{{
              selectedZone
            }}</text>
            <view
              class="i-mdi-chevron-down shrink-0 text-base text-gray-400"
              aria-hidden="true"
            ></view>
          </button>
        </picker>
        <text
          v-if="!filteredTimezones.length"
          class="mt-2 block text-sm text-gray-500"
          >没有匹配的时区，请修改搜索词。</text
        >
      </view>
      <view v-if="loadError" class="space-y-3 text-sm text-gray-500">
        <text>时区列表加载失败，仍可使用当前时区。</text>
        <button
          size="mini"
          class="flex h-11 items-center justify-center rounded-xl bg-blue-50 px-4 text-sm font-medium text-blue-600 active:bg-blue-100"
          :loading="loading"
          :disabled="loading"
          @click="loadOptions"
        >
          重试
        </button>
      </view>
      <!-- 时间预览 -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700"
          >时间预览</text
        >
        <view
          class="rounded-xl bg-gray-50 px-4 py-3 text-sm leading-6 text-gray-800 ring-1 ring-gray-200"
          aria-live="polite"
        >
          <text class="block break-all">预览时区：{{ previewZone }}</text>
          <text class="block">时间预览：{{ previewTime }}</text>
          <text
            v-if="followDevice && !deviceZone"
            class="mt-2 block text-gray-500"
            >当前设备无法识别时区，已使用系统时区；你也可以手动选择。</text
          >
        </view>
        <text class="mt-2 block text-xs leading-5 text-gray-500"
          >用于时间显示、日期筛选和导出。定时任务和业务统计使用各自配置的时区。</text
        >
      </view>
      <text v-if="saveError" class="block text-sm text-red-500" role="alert">{{
        saveError
      }}</text>
      <!-- 保存按钮 -->
      <view class="pt-6">
        <button
          @click="saveTimezone"
          class="flex h-12 w-full items-center justify-center rounded-xl bg-blue-500 text-base font-semibold text-white shadow-lg shadow-blue-500/30 transition-all active:scale-95 active:bg-blue-600"
          :loading="saving"
          :disabled="saving || initializing"
        >
          保存时区
        </button>
      </view>
    </view>
  </view>
</template>

<script>
import { getTimezoneOptions, updateUserTimezone } from "@/api/system/user";
import { formatBusinessTime, getBusinessTimezone, getDeviceTimezone, getDisplayTimezone, getSupportedTimezones } from "@/utils/time";

export default {
  data() {
    return {
      followDevice: this.$store.state.user.timeZone === "auto",
      selectedZone: getDisplayTimezone(),
      timezones: getSupportedTimezones(),
      zoneSearch: "",
      loading: false,
      loadError: false,
      saving: false,
      initializing: true,
      saveError: "",
      now: new Date()
    };
  },
  computed: {
    deviceZone: getDeviceTimezone,
    previewZone() {
      return this.followDevice ? this.deviceZone || getBusinessTimezone() : this.selectedZone;
    },
    previewTime() {
      return formatBusinessTime(this.now, "YYYY-MM-DD HH:mm:ss", this.previewZone);
    },
    filteredTimezones() {
      return this.timezones.filter(zone => zone.toLowerCase().includes(this.zoneSearch.trim().toLowerCase()));
    },
    selectedIndex() {
      return Math.max(0, this.filteredTimezones.indexOf(this.selectedZone));
    }
  },
  async onLoad() {
    await Promise.all([
      this.loadOptions(),
      this.$store.dispatch("GetInfo").then(() => {
        this.followDevice = this.$store.state.user.timeZone === "auto";
        this.selectedZone = getDisplayTimezone();
      }).catch(() => {
        this.saveError = "账号设置读取失败，请重试保存或重新进入页面";
      })
    ]);
    this.initializing = false;
  },
  methods: {
    selectTimezone(event) {
      this.selectedZone = this.filteredTimezones[Number(event.detail.value)];
    },
    async loadOptions() {
      this.loading = true;
      this.loadError = false;
      try {
        const response = await getTimezoneOptions();
        this.timezones = getSupportedTimezones(response.data);
      } catch {
        this.loadError = true;
      } finally {
        this.loading = false;
      }
    },
    async saveTimezone() {
      if (this.saving || this.initializing) return;
      this.saving = true;
      this.saveError = "";
      const preference = this.followDevice ? "auto" : this.selectedZone;
      try {
        await updateUserTimezone(preference);
        await this.$store.dispatch("ApplyTimezone", preference);
        this.now = new Date();
        this.$modal.showToast("时区设置已保存");
      } catch (error) {
        this.saveError = error.message || "保存失败，请重试";
      } finally {
        this.saving = false;
      }
    }
  }
};
</script>

<style>
page {
  height: 100%;
  background-color: #ffffff;
}
</style>
