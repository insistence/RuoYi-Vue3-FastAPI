<script>
import { refreshDeviceTimezone } from "@/utils/time";
import config from "./config";
import { getToken } from "@/utils/auth";

export default {
  onLaunch: function () {
    this.initApp();
  },
  onShow() {
    refreshDeviceTimezone();
  },
  methods: {
    // 初始化应用
    initApp() {
      // 初始化应用配置
      this.initConfig();
      // 检查用户登录状态
      //#ifdef H5
      this.checkLogin();
      //#endif
    },
    initConfig() {
      this.globalData.config = config;
    },
    checkLogin() {
      if (!getToken()) {
        this.$tab.reLaunch("/pages/login");
      }
    },
  },
};
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

/* Hide scrollbar for Chrome/Safari/Webkit */
::-webkit-scrollbar {
  display: none;
  width: 0 !important;
  height: 0 !important;
  -webkit-appearance: none;
  background: transparent;
}
</style>
