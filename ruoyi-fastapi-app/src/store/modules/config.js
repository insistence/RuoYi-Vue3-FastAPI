import { defineStore } from "pinia";
import { ref } from "vue";

export const useConfigStore = defineStore("config", () => {
  const config = ref();
  const setConfig = (val) => {
    config.value = val;
  };
  return {
    config,
    setConfig,
  };
});
