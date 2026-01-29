<template>
  <view class="flex h-full flex-col bg-gray-50 overflow-hidden">
    <scroll-view scroll-y class="flex-1" :show-scrollbar="false">
      <view class="p-4 pb-24 space-y-6">
        <!-- Banner -->
        <view
          class="relative h-40 w-full overflow-hidden rounded-2xl shadow-lg shadow-indigo-100"
        >
          <swiper
            class="h-40 w-full"
            :current="swiperDotIndex"
            @change="changeSwiper"
            autoplay
            interval="3000"
            circular
          >
            <swiper-item v-for="(item, index) in data" :key="index">
              <view class="h-full w-full" @click="clickBannerItem(item)">
                <image
                  :src="item.image"
                  mode="scaleToFill"
                  class="block h-full w-full"
                />
              </view>
            </swiper-item>
          </swiper>
          <!-- Custom Dots -->
          <view
            class="absolute bottom-3 right-0 left-0 flex justify-center space-x-2 pointer-events-none"
          >
            <view
              v-for="(item, index) in data"
              :key="index"
              class="h-1.5 rounded-full transition-all duration-300"
              :class="current === index ? 'bg-white w-4' : 'bg-white/50 w-1.5'"
            >
            </view>
          </view>
        </view>

        <!-- AI Tools Section -->
        <view>
          <view class="mb-4 flex items-center space-x-2">
            <view class="h-4 w-1 rounded-full bg-indigo-500"></view>
            <text class="text-base font-bold text-gray-800">AI 生产力</text>
          </view>
          <view class="grid grid-cols-2 gap-4">
            <view
              class="group relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm transition-all active:scale-95"
              @click="handleToAiChat"
            >
              <view
                class="absolute -right-4 -top-4 size-20 rounded-full bg-indigo-50 opacity-50"
              ></view>
              <view class="relative z-10 flex flex-col">
                <view
                  class="mb-3 flex size-10 items-center justify-center rounded-xl bg-indigo-500 text-white shadow-md shadow-indigo-200"
                >
                  <view class="i-mdi-chat text-xl"></view>
                </view>
                <text class="font-bold text-gray-800">智能对话</text>
                <text class="mt-1 text-xs text-gray-500">智能助手</text>
              </view>
            </view>
            <view
              class="group relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm transition-all active:scale-95"
              @click="handleBuilding"
            >
              <view
                class="absolute -right-4 -top-4 size-20 rounded-full bg-purple-50 opacity-50"
              ></view>
              <view class="relative z-10 flex flex-col">
                <view
                  class="mb-3 flex size-10 items-center justify-center rounded-xl bg-purple-500 text-white shadow-md shadow-purple-200"
                >
                  <view class="i-mdi-image-multiple text-xl"></view>
                </view>
                <text class="font-bold text-gray-800">图像生成</text>
                <text class="mt-1 text-xs text-gray-500">创意工坊</text>
              </view>
            </view>
          </view>
        </view>

        <!-- System Management Section -->
        <view>
          <view class="mb-4 flex items-center space-x-2">
            <view class="h-4 w-1 rounded-full bg-blue-500"></view>
            <text class="text-base font-bold text-gray-800">系统管理</text>
          </view>
          <view class="rounded-2xl bg-white p-5 shadow-sm">
            <view class="flex flex-wrap justify-between gap-y-4">
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleToUserList"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-blue-50 text-blue-500 transition-colors group-active:bg-blue-100"
                >
                  <view class="i-mdi-account text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >用户管理</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-orange-50 text-orange-500 transition-colors group-active:bg-orange-100"
                >
                  <view class="i-mdi-badge-account text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >角色管理</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-green-50 text-green-500 transition-colors group-active:bg-green-100"
                >
                  <view class="i-mdi-office-building text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >部门管理</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-red-50 text-red-500 transition-colors group-active:bg-red-100"
                >
                  <view class="i-mdi-cog text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >配置管理</text
                >
              </view>

              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-cyan-50 text-cyan-500 transition-colors group-active:bg-cyan-100"
                >
                  <view class="i-mdi-book-open-page-variant text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >字典管理</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-yellow-50 text-yellow-500 transition-colors group-active:bg-yellow-100"
                >
                  <view class="i-mdi-bullhorn text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >通知公告</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-pink-50 text-pink-500 transition-colors group-active:bg-pink-100"
                >
                  <view class="i-mdi-file-document-outline text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600"
                  >日志管理</text
                >
              </view>
              <view
                class="w-[22%] flex flex-col items-center space-y-1.5 active:opacity-60"
                @click="handleBuilding"
              >
                <view
                  class="flex size-10 items-center justify-center rounded-xl bg-gray-50 text-gray-500 transition-colors group-active:bg-gray-100"
                >
                  <view class="i-mdi-dots-horizontal text-xl"></view>
                </view>
                <text class="text-[11px] font-medium text-gray-600">更多</text>
              </view>
            </view>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, getCurrentInstance } from "vue";

const { proxy } = getCurrentInstance();
const current = ref(0);
const swiperDotIndex = ref(0);
const data = ref([
  { image: "/static/images/banner/banner01.jpg" },
  { image: "/static/images/banner/banner02.jpg" },
  { image: "/static/images/banner/banner03.jpg" },
]);

function clickBannerItem(item) {
  console.info(item);
}

function changeSwiper(e) {
  current.value = e.detail.current;
}

function handleToAiChat() {
  handleBuilding();
}

function handleToUserList() {
  handleBuilding();
}

function handleBuilding() {
  proxy.$modal.msg("模块建设中~");
}
</script>
