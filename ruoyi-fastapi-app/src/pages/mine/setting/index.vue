<template>
  <view class="flex h-full flex-col overflow-y-auto bg-gray-50 pt-4 pb-10">
    <view class="bg-white">
      <!-- Change Password -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
        @click="handleToPwd"
      >
        <view class="flex items-center">
          <view class="i-mdi-lock text-xl text-gray-600 mr-3"></view>
          <text class="text-base text-gray-800">修改密码</text>
        </view>
        <view class="i-mdi-chevron-right text-base text-gray-400"></view>
      </view>

      <!-- Check Update -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
        @click="handleToUpgrade"
      >
        <view class="flex items-center">
          <view class="i-mdi-refresh text-xl text-gray-600 mr-3"></view>
          <text class="text-base text-gray-800">检查更新</text>
        </view>
        <view class="i-mdi-chevron-right text-base text-gray-400"></view>
      </view>

      <!-- Clean Cache -->
      <view
        class="flex items-center justify-between px-5 py-4 active:bg-gray-50"
        @click="handleCleanTmp"
      >
        <view class="flex items-center">
          <view class="i-mdi-delete text-xl text-gray-600 mr-3"></view>
          <text class="text-base text-gray-800">清理缓存</text>
        </view>
        <view class="i-mdi-chevron-right text-base text-gray-400"></view>
      </view>
    </view>

    <!-- Logout -->
    <view class="mt-8 px-4">
      <view
        class="flex h-12 w-full items-center justify-center rounded-xl bg-red-50 text-base font-semibold text-red-600 transition-colors active:bg-red-100"
        @click="handleLogout"
        >退出登录</view
      >
    </view>
  </view>
</template>

<script setup>
import { useUserStore } from "@/store";
import { getCurrentInstance } from "vue";

const { proxy } = getCurrentInstance();

function handleToPwd() {
  proxy.$tab.navigateTo("/pages/mine/pwd/index");
}

function handleToUpgrade() {
  proxy.$modal.showToast("模块建设中~");
}

function handleCleanTmp() {
  proxy.$modal.showToast("模块建设中~");
}

function handleLogout() {
  proxy.$modal.confirm("确定注销并退出系统吗？").then(() => {
    useUserStore()
      .logOut()
      .then(() => {})
      .finally(() => {
        proxy.$tab.reLaunch("/pages/index");
      });
  });
}
</script>

<style>
page {
  height: 100%;
  background-color: #f9fafb;
}
</style>
