<template>
  <div class="linkGroup">
    <a v-for="(item, index) in links" :key="index" :href="item.href">
      {{ item.title }}
    </a>
    <a-button size="small" type="primary" ghost>
      <PlusOutlined /> 添加
    </a-button>
  </div>
</template>

<script>
import { Button } from "ant-design-vue";

export default {
  components: {
    AButton: Button,
  },
};
</script>

<script setup>
import { PlusOutlined } from "@ant-design/icons-vue";

const links = [
  {
    title: "操作一",
    href: "",
  },
  {
    title: "操作二",
    href: "",
  },
  {
    title: "操作三",
    href: "",
  },
  {
    title: "操作四",
    href: "",
  },
  {
    title: "操作五",
    href: "",
  },
  {
    title: "操作六",
    href: "",
  },
];
</script>

<style scoped lang="less">
.linkGroup {
  padding: 20px 0 8px 24px;
  font-size: 0;
  & > a {
    display: inline-block;
    width: 25%;
    margin-bottom: 13px;
    color: var(--el-text-color-regular);
    font-size: 14px;
    &:hover {
      color: var(--el-color-primary);
    }
  }
}
</style>