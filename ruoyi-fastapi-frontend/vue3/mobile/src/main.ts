// @ts-nocheck
import { createSSRApp } from "vue";
import App from "./App.vue";
import store from "./store"; // store
import { install } from "./plugins"; // plugins
import "./permission"; // permission
import { useDict } from "@/utils/dict";

export function createApp() {
  const app = createSSRApp(App);
  app.use(store);
  app.config.globalProperties.useDict = useDict;
  install(app);
  return {
    app,
  };
}
