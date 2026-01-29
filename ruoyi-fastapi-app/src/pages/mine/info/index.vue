<template>
  <view class="flex h-full flex-col overflow-y-auto bg-gray-50 pt-4 pb-10">
    <view class="overflow-hidden bg-white shadow-sm">
      <!-- Nickname -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-blue-50 text-blue-500"
          >
            <view class="i-mdi-account text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">昵称</text>
        </view>
        <text class="text-sm text-gray-500">{{ user.nickName }}</text>
      </view>

      <!-- Phone -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-green-50 text-green-500"
          >
            <view class="i-mdi-phone text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">手机号码</text>
        </view>
        <text class="text-sm text-gray-500">{{ user.phonenumber }}</text>
      </view>

      <!-- Email -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-indigo-50 text-indigo-500"
          >
            <view class="i-mdi-email text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">邮箱</text>
        </view>
        <text class="text-sm text-gray-500">{{ user.email }}</text>
      </view>

      <!-- Post -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-orange-50 text-orange-500"
          >
            <view class="i-mdi-shield-account text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">岗位</text>
        </view>
        <text class="text-sm text-gray-500">{{ postGroup }}</text>
      </view>

      <!-- Role -->
      <view
        class="flex items-center justify-between border-b border-gray-100 px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-purple-50 text-purple-500"
          >
            <view class="i-mdi-badge-account text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">角色</text>
        </view>
        <text class="text-sm text-gray-500">{{ roleGroup }}</text>
      </view>

      <!-- Create Time -->
      <view
        class="flex items-center justify-between px-5 py-4 active:bg-gray-50"
      >
        <view class="flex items-center">
          <view
            class="flex size-9 items-center justify-center rounded-full bg-pink-50 text-pink-500"
          >
            <view class="i-mdi-calendar text-xl"></view>
          </view>
          <text class="ml-3 text-base font-medium text-gray-800">创建日期</text>
        </view>
        <text class="text-sm text-gray-500">{{ user.createTime }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { getUserProfile } from "@/api/system/user";
import { ref } from "vue";

const user = ref({});
const roleGroup = ref("");
const postGroup = ref("");

function getUser() {
  getUserProfile().then((response) => {
    user.value = response.data;
    roleGroup.value = response.roleGroup;
    postGroup.value = response.postGroup;
  });
}

getUser();
</script>

<style>
page {
  height: 100%;
  background-color: #f9fafb;
}
</style>
