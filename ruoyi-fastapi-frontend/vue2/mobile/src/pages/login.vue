<template>
  <view
    class="flex h-full flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-6 pb-20 overflow-hidden"
  >
    <!-- Logo Section -->
    <view class="mb-6 flex flex-col items-center">
      <view
        class="mb-4 flex size-16 items-center justify-center rounded-2xl bg-white shadow-lg"
      >
        <image
          class="size-10"
          :src="globalConfig.appInfo.logo"
          mode="widthFix"
        />
      </view>
      <text class="text-xl font-bold tracking-wide text-gray-800"
        >RuoYi-FastAPI移动端登录</text
      >
    </view>

    <!-- Form Section -->
    <view class="w-full rounded-3xl bg-white/80 p-6 shadow-xl backdrop-blur-md">
      <!-- Username -->
      <view class="group relative mb-5">
        <view
          class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 transition-colors group-focus-within:text-blue-500"
        >
          <view class="i-mdi-account text-xl"></view>
        </view>
        <input
          v-model="loginForm.username"
          class="h-12 w-full rounded-xl bg-gray-50 pl-12 pr-4 text-sm text-gray-700 outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-400"
          type="text"
          placeholder="请输入账号"
          maxlength="30"
        />
      </view>

      <!-- Password -->
      <view class="group relative mb-5">
        <view
          class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 transition-colors group-focus-within:text-blue-500"
        >
          <view class="i-mdi-lock text-xl"></view>
        </view>
        <input
          v-model="loginForm.password"
          type="password"
          class="h-12 w-full rounded-xl bg-gray-50 pl-12 pr-4 text-sm text-gray-700 outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-400"
          placeholder="请输入密码"
          maxlength="20"
        />
      </view>

      <!-- Captcha -->
      <view
        class="mb-8 flex items-center justify-between"
        v-if="captchaEnabled"
      >
        <view class="group relative mr-3 flex-1">
          <view
            class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 transition-colors group-focus-within:text-blue-500"
          >
            <view class="i-mdi-security text-xl"></view>
          </view>
          <input
            v-model="loginForm.code"
            type="number"
            class="h-12 w-full rounded-xl bg-gray-50 pl-12 pr-4 text-sm text-gray-700 outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-400"
            placeholder="验证码"
            maxlength="4"
          />
        </view>
        <view
          class="h-12 w-28 overflow-hidden rounded-xl bg-gray-100 shadow-sm transition-opacity active:opacity-80"
          @click="getCode"
        >
          <image :src="codeUrl" class="h-full w-full object-cover"></image>
        </view>
      </view>

      <!-- Login Button -->
      <button
        @click="handleLogin"
        class="flex h-12 w-full items-center justify-center rounded-xl bg-gradient-to-r from-blue-500 to-indigo-600 text-base font-semibold text-white shadow-lg shadow-blue-500/30 transition-transform active:scale-95"
      >
        登 录
      </button>

      <!-- Footer Links -->
      <view class="mt-6 flex flex-col items-center space-y-3">
        <view class="flex items-center text-sm text-gray-500" v-if="register">
          <text>没有账号？</text>
          <text
            @click="handleUserRegister"
            class="ml-1 font-medium text-blue-600 active:opacity-70"
            >立即注册</text
          >
        </view>

        <view
          class="flex flex-wrap items-center justify-center text-xs text-gray-400"
        >
          <text>登录即代表同意</text>
          <text
            @click="handleUserAgrement"
            class="mx-1 text-blue-500 active:opacity-70"
            >《用户协议》</text
          >
          <text>和</text>
          <text
            @click="handlePrivacy"
            class="mx-1 text-blue-500 active:opacity-70"
            >《隐私协议》</text
          >
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { getCodeImg } from "@/api/login";
import { getToken } from "@/utils/auth";

export default {
  data() {
    return {
      codeUrl: "",
      captchaEnabled: true,
      // 用户注册开关
      register: false,
      globalConfig: getApp().globalData.config,
      loginForm: {
        username: "admin",
        password: "admin123",
        code: "",
        uuid: "",
      },
    };
  },
  created() {
    this.getCode();
  },
  onLoad() {
    //#ifdef H5
    if (getToken()) {
      this.$tab.reLaunch("/pages/index");
    }
    //#endif
  },
  methods: {
    // 用户注册
    handleUserRegister() {
      this.$tab.redirectTo(`/pages/register`);
    },
    // 隐私协议
    handlePrivacy() {
      this.$tab.navigateTo(`/pages/common/privacy/index`);
    },
    // 用户协议
    handleUserAgrement() {
      this.$tab.navigateTo(`/pages/common/agreement/index`);
    },
    // 获取图形验证码
    getCode() {
      getCodeImg().then((res) => {
        this.captchaEnabled =
          res.captchaEnabled === undefined ? true : res.captchaEnabled;
        if (this.captchaEnabled) {
          this.codeUrl = "data:image/gif;base64," + res.img;
          this.loginForm.uuid = res.uuid;
        }
      });
    },
    // 登录方法
    async handleLogin() {
      if (this.loginForm.username === "") {
        this.$modal.msgError("请输入账号");
      } else if (this.loginForm.password === "") {
        this.$modal.msgError("请输入密码");
      } else if (this.loginForm.code === "" && this.captchaEnabled) {
        this.$modal.msgError("请输入验证码");
      } else {
        this.$modal.loading("登录中，请耐心等待...");
        this.pwdLogin();
      }
    },
    // 密码登录
    async pwdLogin() {
      this.$store
        .dispatch("Login", this.loginForm)
        .then(() => {
          this.$modal.closeLoading();
          this.loginSuccess();
        })
        .catch(() => {
          if (this.captchaEnabled) {
            this.getCode();
          }
        });
    },
    // 登录成功后，处理函数
    loginSuccess(result) {
      // 设置用户信息
      this.$store.dispatch("GetInfo").then((res) => {
        this.$tab.reLaunch("/pages/index");
      });
    },
  },
};
</script>

<style lang="scss" scoped>
page {
  background-color: #ffffff;
}
</style>
