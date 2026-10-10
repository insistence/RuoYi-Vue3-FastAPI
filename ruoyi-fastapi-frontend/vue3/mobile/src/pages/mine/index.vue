<template>
  <view class="flex h-full flex-col bg-gray-50 overflow-hidden">
    <!-- Header Section -->
    <view
      class="relative overflow-hidden bg-gradient-to-r from-blue-500 to-indigo-600 pb-20 pt-16 text-white shadow-lg"
    >
      <view
        class="absolute -right-10 -top-10 size-64 rounded-full bg-white/10 blur-3xl"
      ></view>
      <view
        class="absolute -bottom-10 -left-10 size-40 rounded-full bg-white/10 blur-2xl"
      ></view>

      <view class="relative z-10 flex items-center justify-between px-6">
        <view class="flex items-center space-x-4">
          <!-- Avatar -->
          <view
            class="relative overflow-hidden rounded-full border-4 border-white/30 bg-white/20 shadow-xl transition-transform active:scale-95"
          >
            <image
              v-if="avatar"
              @click="handleToAvatar"
              :src="avatar"
              class="size-20 object-cover"
            />
            <view
              v-else
              class="flex size-20 items-center justify-center bg-white text-gray-400"
            >
              <view class="i-mdi-account text-5xl"></view>
            </view>
          </view>

          <!-- User Info -->
          <view class="flex flex-col">
            <template v-if="name">
              <view
                class="text-xl font-bold tracking-wide"
                @click="handleToInfo"
              >
                {{ name }}
              </view>
              <view
                class="mt-1 flex items-center text-sm text-blue-100"
                @click="handleToInfo"
              >
                <text>查看个人信息</text>
                <view class="i-mdi-chevron-right ml-1 text-xs"></view>
              </view>
            </template>
            <view v-else class="text-xl font-bold" @click="handleToLogin">
              点击登录
            </view>
          </view>
        </view>
      </view>
    </view>

    <!-- Content Section -->
    <view class="relative z-20 -mt-12 flex-1 px-4 overflow-y-auto">
      <!-- Quick Actions -->
      <view
        class="mb-4 flex items-center justify-between rounded-2xl bg-white p-4 shadow-lg shadow-gray-200/50"
      >
        <view
          class="flex flex-1 flex-col items-center justify-center space-y-2 active:opacity-70"
          @click="handleJiaoLiuQun"
        >
          <view
            class="flex size-12 items-center justify-center rounded-full bg-pink-50 text-pink-500"
          >
            <view class="i-mdi-account-group text-2xl"></view>
          </view>
          <text class="text-xs font-medium text-gray-600">交流群</text>
        </view>
        <view
          class="flex flex-1 flex-col items-center justify-center space-y-2 active:opacity-70"
          @click="handleBuilding"
        >
          <view
            class="flex size-12 items-center justify-center rounded-full bg-blue-50 text-blue-500"
          >
            <view class="i-mdi-face-agent text-2xl"></view>
          </view>
          <text class="text-xs font-medium text-gray-600">在线客服</text>
        </view>
        <view
          class="flex flex-1 flex-col items-center justify-center space-y-2 active:opacity-70"
          @click="handleBuilding"
        >
          <view
            class="flex size-12 items-center justify-center rounded-full bg-purple-50 text-purple-500"
          >
            <view class="i-mdi-forum text-2xl"></view>
          </view>
          <text class="text-xs font-medium text-gray-600">反馈社区</text>
        </view>
        <view
          class="flex flex-1 flex-col items-center justify-center space-y-2 active:opacity-70"
          @click="handleBuilding"
        >
          <view
            class="flex size-12 items-center justify-center rounded-full bg-green-50 text-green-500"
          >
            <view class="i-mdi-thumb-up text-2xl"></view>
          </view>
          <text class="text-xs font-medium text-gray-600">点赞我们</text>
        </view>
      </view>

      <!-- Menu List -->
      <view
        class="overflow-hidden rounded-2xl bg-white shadow-lg shadow-gray-200/50"
      >
        <view
          class="group flex items-center justify-between border-b border-gray-100 p-4 transition-colors active:bg-gray-50"
          @click="handleToEditInfo"
        >
          <view class="flex items-center space-x-3">
            <view class="i-mdi-account-edit text-xl text-blue-500"></view>
            <text class="text-base text-gray-700">编辑资料</text>
          </view>
          <view class="i-mdi-chevron-right text-gray-400"></view>
        </view>

        <view
          class="group flex items-center justify-between border-b border-gray-100 p-4 transition-colors active:bg-gray-50"
          @click="handleHelp"
        >
          <view class="flex items-center space-x-3">
            <view class="i-mdi-help-circle text-xl text-orange-500"></view>
            <text class="text-base text-gray-700">常见问题</text>
          </view>
          <view class="i-mdi-chevron-right text-gray-400"></view>
        </view>

        <view
          class="group flex items-center justify-between border-b border-gray-100 p-4 transition-colors active:bg-gray-50"
          @click="handleAbout"
        >
          <view class="flex items-center space-x-3">
            <view class="i-mdi-heart-outline text-xl text-red-500"></view>
            <text class="text-base text-gray-700">关于我们</text>
          </view>
          <view class="i-mdi-chevron-right text-gray-400"></view>
        </view>

        <view
          class="group flex items-center justify-between p-4 transition-colors active:bg-gray-50"
          @click="handleToSetting"
        >
          <view class="flex items-center space-x-3">
            <view class="i-mdi-cog-outline text-xl text-gray-500"></view>
            <text class="text-base text-gray-700">应用设置</text>
          </view>
          <view class="i-mdi-chevron-right text-gray-400"></view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { useUserStore } from "@/store";
import { computed, getCurrentInstance } from "vue";

const { proxy } = getCurrentInstance();
const userStore = useUserStore();

const name = computed(() => userStore.name);
const avatar = computed(() => userStore.avatar);
const windowHeight = computed(() => uni.getSystemInfoSync().windowHeight - 50);

function handleToInfo() {
  proxy.$tab.navigateTo("/pages/mine/info/index");
}

function handleToEditInfo() {
  proxy.$tab.navigateTo("/pages/mine/info/edit");
}

function handleToSetting() {
  proxy.$tab.navigateTo("/pages/mine/setting/index");
}

function handleToLogin() {
  proxy.$tab.reLaunch("/pages/login");
}

function handleToAvatar() {
  proxy.$tab.navigateTo("/pages/mine/avatar/index");
}

function handleHelp() {
  proxy.$tab.navigateTo("/pages/mine/help/index");
}

function handleAbout() {
  proxy.$tab.navigateTo("/pages/mine/about/index");
}

function handleJiaoLiuQun() {
  proxy.$modal.showToast("模块建设中~");
}

function handleBuilding() {
  proxy.$modal.showToast("模块建设中~");
}
</script>
