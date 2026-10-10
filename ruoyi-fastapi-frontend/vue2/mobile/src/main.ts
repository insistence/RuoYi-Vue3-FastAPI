// @ts-nocheck
import Vue from "vue";
import App from "./App.vue";
import store from "./store";
import plugins from "./plugins";
import "./permission";
import { getDicts } from "@/api/system/dict/data";

Vue.use(plugins);
Vue.config.productionTip = false;
Vue.prototype.$store = store;
Vue.prototype.getDicts = getDicts;
App.mpType = "app";
const app = new Vue({
  ...App,
});
app.$mount();
