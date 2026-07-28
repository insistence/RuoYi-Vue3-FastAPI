<template>
  <div class="ai-message-container">
    <div v-if="reasoningContent" class="reasoning-section">
      <div class="reasoning-header" @click="toggleReasoning">
        <el-icon :class="{ 'is-expanded': isReasoningExpanded }"
          ><ArrowRight
        /></el-icon>
        <span>深度思考过程</span>
        <span class="reasoning-status" v-if="!isThinkingComplete"
          >思考中...</span
        >
      </div>
      <div v-show="isReasoningExpanded" class="reasoning-content">
        <MarkdownRender :content="reasoningContent" :is-dark="isDark" />
      </div>
    </div>
    <div class="ai-message-content">
      <MarkdownRender :content="content" :is-dark="isDark" />
    </div>
    <div
      v-if="loading && !content && !reasoningContent"
      class="typing-indicator"
    >
      <span></span>
      <span></span>
      <span></span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { MarkdownRender } from "markstream-vue";
import { useDark } from "@vueuse/core";
import { enableKatex, enableMermaid } from "markstream-vue";
import "markstream-vue/index.css";
import "katex/dist/katex.min.css";

enableMermaid();
enableKatex();

const isDark = useDark();

const props = defineProps({
  content: {
    type: String,
    default: "",
  },
  reasoningContent: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const isReasoningExpanded = ref(true);

const isThinkingComplete = computed(() => {
  return !!props.content;
});

function toggleReasoning() {
  isReasoningExpanded.value = !isReasoningExpanded.value;
}
</script>

<style lang="scss">
.ai-message-container {
  width: 100%;

  .ai-message-content {
    font-size: 14px;
    line-height: 1.6;
    color: var(--el-text-color-primary);
    overflow-wrap: break-word;
    word-break: break-word;
  }
}

.reasoning-section {
  margin-bottom: 15px;
  border-left: 2px solid var(--el-border-color);
  padding-left: 10px;

  .reasoning-header {
    display: flex;
    align-items: center;
    cursor: pointer;
    color: var(--el-text-color-secondary);
    font-size: 13px;
    user-select: none;
    margin-bottom: 5px;

    .el-icon {
      margin-right: 4px;
      transition: transform 0.3s;
      &.is-expanded {
        transform: rotate(90deg);
      }
    }

    .reasoning-status {
      margin-left: 10px;
      font-size: 12px;
      color: #e6a23c;
      animation: blink 1.5s infinite;
    }
  }

  .reasoning-content {
    font-size: 13px;
    color: var(--el-text-color-regular);
    padding: 8px;
    background-color: var(--el-fill-color-light);
    border-radius: 4px;
    overflow-wrap: break-word;
    word-break: break-word;
  }
}

@keyframes blink {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}

.typing-indicator {
  display: flex;
  align-items: center;
  padding: 8px 0;

  span {
    display: inline-block;
    width: 6px;
    height: 6px;
    background-color: var(--el-text-color-secondary);
    border-radius: 50%;
    animation: typing 1.4s infinite ease-in-out both;
    margin-right: 4px;

    &:nth-child(1) {
      animation-delay: -0.32s;
    }

    &:nth-child(2) {
      animation-delay: -0.16s;
    }
  }
}

@keyframes typing {
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>
