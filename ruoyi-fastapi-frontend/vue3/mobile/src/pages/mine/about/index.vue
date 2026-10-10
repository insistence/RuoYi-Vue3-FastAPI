<template>
  <view class="flex h-full flex-col bg-gray-50 pb-10">
    <!-- Header -->
    <view class="flex flex-col items-center py-10">
      <image
        class="size-20 rounded-xl shadow-md"
        src="/static/logo200.png"
        mode="widthFix"
      />
      <text class="mt-4 text-xl font-bold text-gray-800"
        >RuoYi-FastAPI移动端</text
      >
    </view>

    <!-- Info List -->
    <view class="bg-white">
      <!-- Version -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4"
      >
        <text class="text-base text-gray-800">版本信息</text>
        <text class="text-sm text-gray-500">v{{ version }}</text>
      </view>

      <!-- Email -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4"
      >
        <text class="text-base text-gray-800">官方邮箱</text>
        <text class="text-sm text-gray-500">xxx@xxx.com</text>
      </view>

      <!-- Hotline -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4"
      >
        <text class="text-base text-gray-800">服务热线</text>
        <text class="text-sm text-gray-500">400-999-9999</text>
      </view>

      <!-- Website -->
      <view class="flex items-center justify-between px-5 py-4">
        <text class="text-base text-gray-800">公司网站</text>
        <text class="text-sm text-blue-500 underline active:opacity-70">{{
          url
        }}</text>
      </view>
    </view>

    <!-- Copyright -->
    <view class="mt-10 text-center text-xs text-gray-400">
      Copyright &copy; 2026 insistence.tech All Rights Reserved.
    </view>
  </view>
</template>

<script setup>
import { useConfigStore } from "@/store";

const url = useConfigStore().config.appInfo.site_url;
const version = useConfigStore().config.appInfo.version;
</script>

<style>
page {
  background-color: #f9fafb;
}
</style>
