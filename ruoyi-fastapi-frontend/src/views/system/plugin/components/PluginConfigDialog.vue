<template>
   <el-dialog :title="title" :model-value="modelValue" width="720px" append-to-body @update:model-value="emit('update:modelValue', $event)">
      <el-form ref="configRef" :model="configForm" label-width="120px">
         <el-empty v-if="!items.length" description="暂无插件配置" />
         <div v-for="group in configGroups" :key="group.name" class="plugin-config-section">
            <div v-if="configGroups.length > 1 || group.name !== 'default'" class="plugin-config-section-title">{{ formatConfigGroupLabel(group.name) }}</div>
            <el-form-item
               v-for="item in group.items"
               :key="item.key"
               :label="item.label || item.key"
               :prop="'values.' + item.key"
               :rules="getConfigItemRules(item)"
               class="plugin-config-item"
            >
               <el-switch v-if="item.type === 'boolean'" v-model="configForm.values[item.key]" />
               <el-input-number
                  v-else-if="item.type === 'number'"
                  v-model="configForm.values[item.key]"
                  :min="item.min ?? undefined"
                  :max="item.max ?? undefined"
                  :placeholder="getConfigInputPlaceholder(item)"
                  class="plugin-config-control"
               />
               <el-select
                  v-else-if="item.type === 'select'"
                  v-model="configForm.values[item.key]"
                  :placeholder="getConfigInputPlaceholder(item)"
                  class="plugin-config-control"
               >
                  <el-option
                     v-for="option in item.options || []"
                     :key="String(option.value)"
                     :label="option.label"
                     :value="option.value"
                  />
               </el-select>
               <template v-else-if="item.type === 'textarea' || item.type === 'json'">
                  <el-input
                     v-model="configForm.values[item.key]"
                     type="textarea"
                     :rows="4"
                     :placeholder="getConfigInputPlaceholder(item)"
                     class="plugin-config-control"
                  />
                  <div v-if="item.type === 'json'" class="config-inline-actions">
                     <el-button link type="primary" icon="MagicStick" @click="formatConfigJsonValue(item)">格式化 JSON</el-button>
                  </div>
               </template>
               <el-input
                  v-else
                  v-model="configForm.values[item.key]"
                  :type="isSecretConfigItem(item) ? 'password' : 'text'"
                  :show-password="isSecretConfigItem(item)"
                  :placeholder="getConfigInputPlaceholder(item)"
                  class="plugin-config-control"
               />
               <div class="config-help">
                  <span v-if="item.description" class="config-help-text">{{ item.description }}</span>
                  <div v-if="hasConfigMeta(item)" class="config-meta-list">
                     <el-tag size="small" type="info" effect="plain">{{ item.key }}</el-tag>
                     <el-tag v-if="item.required" size="small" type="warning" effect="plain">必填</el-tag>
                     <el-tag v-if="item.secret" size="small" type="warning" effect="plain">敏感</el-tag>
                     <el-tag v-if="formatConfigDefaultValue(item) !== '-'" size="small" type="info" effect="plain">默认 {{ formatConfigDefaultValue(item) }}</el-tag>
                     <el-tag v-if="formatConfigConstraint(item) !== '-'" size="small" type="info" effect="plain">{{ formatConfigConstraint(item) }}</el-tag>
                  </div>
               </div>
            </el-form-item>
         </div>
      </el-form>
      <template #footer>
         <div class="dialog-footer">
            <el-button
               type="primary"
               :disabled="!items.length"
               :loading="loading"
               @click="submit"
               v-hasPermi="['system:plugin:edit']"
            >保 存</el-button>
            <el-button @click="emit('update:modelValue', false)">关 闭</el-button>
         </div>
      </template>
   </el-dialog>
</template>

<script setup name="PluginConfigDialog">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: "插件配置"
  },
  items: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  formatConfigDefaultValue: {
    type: Function,
    required: true
  },
  formatConfigConstraint: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["update:modelValue", "submit"]);
const configRef = ref(null);
const configForm = reactive({
  values: {}
});

const configGroups = computed(() => {
  const groups = new Map();
  const sortedItems = [...props.items].sort((left, right) => {
    const leftGroup = left.group || "default";
    const rightGroup = right.group || "default";
    if (leftGroup !== rightGroup) {
      return leftGroup.localeCompare(rightGroup);
    }
    const leftOrder = Number(left.order || 0);
    const rightOrder = Number(right.order || 0);
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return String(left.key || "").localeCompare(String(right.key || ""));
  });
  sortedItems.forEach(item => {
    const groupName = item.group || "default";
    if (!groups.has(groupName)) {
      groups.set(groupName, []);
    }
    groups.get(groupName).push(item);
  });
  return Array.from(groups, ([name, items]) => ({ name, items }));
});

watch(
  () => props.items,
  items => {
    configForm.values = {};
    items.forEach(item => {
      configForm.values[item.key] = normalizeConfigValueForForm(item);
    });
  },
  { immediate: true }
);

function submit() {
  configRef.value?.validate(valid => {
    if (!valid) {
      return;
    }
    let values;
    try {
      values = buildConfigSubmitValues();
    } catch (error) {
      ElMessage.error(error.message || "配置格式不正确");
      return;
    }
    emit("submit", values);
  });
}

function normalizeConfigValueForForm(item) {
  if (item.type !== "json") {
    return item.value;
  }
  if (item.value === null || item.value === undefined || item.value === "") {
    return "";
  }
  if (typeof item.value === "string") {
    return item.value;
  }
  return JSON.stringify(item.value, null, 2);
}

function buildConfigSubmitValues() {
  return props.items.reduce((values, item) => {
    const value = configForm.values[item.key];
    if (item.type === "json" && typeof value === "string" && value.trim()) {
      try {
        values[item.key] = JSON.parse(value);
      } catch {
        throw new Error((item.label || item.key) + " 不是合法 JSON");
      }
      return values;
    }
    values[item.key] = value;
    return values;
  }, {});
}

function getConfigItemRules(item) {
  const rules = [];
  if (item.required) {
    rules.push({ required: true, message: "不能为空", trigger: item.type === "select" ? "change" : "blur" });
  }
  if (item.type === "number") {
    rules.push({ validator: buildNumberConfigValidator(item), trigger: "change" });
  }
  if (item.pattern && ["string", "textarea", "password"].includes(item.type)) {
    rules.push({ validator: buildPatternConfigValidator(item), trigger: "blur" });
  }
  if (item.type === "json") {
    rules.push({ validator: validateJsonConfig, trigger: "blur" });
  }
  return rules;
}

function isSecretConfigItem(item) {
  return item.type === "password" || item.secret;
}

function buildNumberConfigValidator(item) {
  return (_rule, value, callback) => {
    if (value === undefined || value === null || value === "") {
      callback();
      return;
    }
    const numberValue = Number(value);
    if (Number.isNaN(numberValue)) {
      callback(new Error("请输入数字"));
      return;
    }
    if (item.min !== undefined && item.min !== null && numberValue < Number(item.min)) {
      callback(new Error("不能小于 " + item.min));
      return;
    }
    if (item.max !== undefined && item.max !== null && numberValue > Number(item.max)) {
      callback(new Error("不能大于 " + item.max));
      return;
    }
    callback();
  };
}

function buildPatternConfigValidator(item) {
  return (_rule, value, callback) => {
    if (value === undefined || value === null || value === "") {
      callback();
      return;
    }
    try {
      if (!new RegExp(item.pattern).test(String(value))) {
        callback(new Error("格式不符合要求"));
        return;
      }
    } catch {
      callback(new Error("配置正则表达式无效"));
      return;
    }
    callback();
  };
}

function validateJsonConfig(_rule, value, callback) {
  if (value === undefined || value === null || value === "") {
    callback();
    return;
  }
  try {
    JSON.parse(value);
    callback();
  } catch {
    callback(new Error("请输入合法 JSON"));
  }
}

function formatConfigJsonValue(item) {
  const value = configForm.values[item.key];
  if (value === undefined || value === null || value === "") {
    return;
  }
  try {
    configForm.values[item.key] = JSON.stringify(typeof value === "string" ? JSON.parse(value) : value, null, 2);
  } catch {
    ElMessage.error((item.label || item.key) + " 不是合法 JSON");
  }
}

function getConfigInputPlaceholder(item) {
  return item.placeholder || item.description || "";
}

function hasConfigMeta(item) {
  return Boolean(
    item.key ||
      item.required ||
      item.secret ||
      props.formatConfigDefaultValue(item) !== "-" ||
      props.formatConfigConstraint(item) !== "-"
  );
}

function formatConfigGroupLabel(groupName) {
  const groupMap = {
    default: "基础配置",
    model: "模型配置",
    security: "安全配置",
    advanced: "高级配置"
  };
  return groupMap[groupName] || groupName;
}
</script>

<style scoped>
.config-help {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 18px;
}

.config-help-text {
  display: block;
}

.config-inline-actions {
  width: 100%;
  margin-top: 4px;
  line-height: 20px;
}

.config-meta-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.plugin-config-control {
  width: 320px;
  max-width: 100%;
}

.plugin-config-control :deep(.el-input__wrapper) {
  width: 100%;
}

.plugin-config-item {
  margin-bottom: 18px;
}

.plugin-config-section + .plugin-config-section {
  margin-top: 6px;
}

.plugin-config-section-title {
  padding-left: 120px;
  margin: 0 0 10px;
  color: #606266;
  font-size: 13px;
  font-weight: 600;
}
</style>
