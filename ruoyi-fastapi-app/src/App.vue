<script setup>
import config from "./config";
import { getToken } from "@/utils/auth";
import { useConfigStore } from "@/store";
import { getCurrentInstance } from "vue";
import { onLaunch } from "@dcloudio/uni-app";

const { proxy } = getCurrentInstance();

onLaunch(() => {
  initApp();
});

// 初始化应用
function initApp() {
  // 初始化应用配置
  initConfig();
  // 检查用户登录状态
  //#ifdef H5
  checkLogin();
  //#endif
}

function initConfig() {
  useConfigStore().setConfig(config);
}

function checkLogin() {
  if (!getToken()) {
    proxy.$tab.reLaunch("/pages/login");
  }
}
</script>

<style>
@tailwind base;
@tailwind components;
@tailwind utilities;

/* Global Reset for UniApp/Mobile */
page,
body {
  height: 100%;
  min-height: 100%;
  overflow-x: hidden;
  /* Prevent default bounce effect on iOS if needed, or just handle overflow */
}

/* Global box-sizing for consistency with Tailwind preflight */
page,
view,
scroll-view,
image,
text,
button,
input,
textarea,
label,
navigator {
  box-sizing: border-box;
}

/* 修复 H5 端 uni.showToast 图标在引入 Tailwind 后可能偏左的问题 */
/* #ifdef H5 */
uni-toast img,
uni-toast svg {
  display: inline-block !important;
}
/* #endif */

/* Hide scrollbar for Chrome/Safari/Webkit */
::-webkit-scrollbar {
  display: none;
  width: 0 !important;
  height: 0 !important;
  -webkit-appearance: none;
  background: transparent;
}
</style>
