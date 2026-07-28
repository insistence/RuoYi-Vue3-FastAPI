import json
import re
from pathlib import Path
from typing import Literal, cast

from .frontend_vue2 import PluginVue2FrontendScaffoldTemplateBuilder
from .naming import PluginScaffoldNaming

FrontendVersion = Literal['vue2', 'vue3']


class PluginFrontendVersionResolver:
    """
    前端 Vue 版本解析器。
    """

    AUTO = 'auto'
    DEFAULT_VERSION: FrontendVersion = 'vue3'
    SUPPORTED_VALUES = (AUTO, 'vue2', 'vue3')

    @classmethod
    def resolve(cls, frontend_root: Path, requested_version: str = AUTO) -> FrontendVersion:
        """
        解析脚手架应使用的 Vue 版本。

        显式版本优先；auto 模式读取目标前端 package.json。临时目录等没有
        package.json 的场景保持历史行为，默认生成 Vue 3 模板。

        :param frontend_root: 前端项目根目录
        :param requested_version: auto、vue2 或 vue3
        :return: 解析后的 Vue 版本
        """
        normalized_version = (requested_version or cls.AUTO).strip().lower()
        if normalized_version not in cls.SUPPORTED_VALUES:
            supported = '、'.join(cls.SUPPORTED_VALUES)
            raise ValueError(f'frontend_version 仅支持 {supported}，当前值：{requested_version}')
        if normalized_version != cls.AUTO:
            return cast('FrontendVersion', normalized_version)

        package_json_path = frontend_root / 'package.json'
        if not package_json_path.is_file():
            return cls.DEFAULT_VERSION

        try:
            package_payload = json.loads(package_json_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'读取前端 package.json 失败：{package_json_path}（{exc}）') from exc
        if not isinstance(package_payload, dict):
            raise ValueError(f'前端 package.json 顶层必须是对象：{package_json_path}')

        dependencies = cls._collect_dependencies(package_payload)
        vue_version = cls._resolve_vue_dependency(dependencies.get('vue'))
        if vue_version is not None:
            return vue_version
        if 'element-ui' in dependencies:
            return 'vue2'
        if 'element-plus' in dependencies:
            return 'vue3'

        raise ValueError(f'无法从 {package_json_path} 识别 Vue 版本，请使用 --frontend-version vue2 或 vue3 显式指定')

    @staticmethod
    def _collect_dependencies(package_payload: dict[str, object]) -> dict[str, object]:
        """
        合并 dependencies 和 devDependencies。

        :param package_payload: package.json 负载
        :return: 依赖映射
        """
        dependencies: dict[str, object] = {}
        for key in ('devDependencies', 'dependencies'):
            section = package_payload.get(key)
            if isinstance(section, dict):
                dependencies.update(section)
        return dependencies

    @staticmethod
    def _resolve_vue_dependency(version_spec: object) -> FrontendVersion | None:
        """
        从 npm Vue 版本约束中提取主版本。

        :param version_spec: Vue npm 版本约束
        :return: Vue 版本，无法识别时返回 None
        """
        if not isinstance(version_spec, str):
            return None
        match = re.search(r'(?<!\d)([23])(?:\.\d+)?', version_spec)
        if match is None:
            return None
        return cast('FrontendVersion', f'vue{match.group(1)}')


class PluginVue3FrontendScaffoldTemplateBuilder:
    """
    前端插件模板内容构建器。
    """

    @staticmethod
    def build_api(plugin_id: str) -> str:
        """
        构建前端 API 模板内容。

        :param plugin_id: 插件ID
        :return: 前端 API 模板内容
        """
        return f"""import request from '@/utils/request'

export function ping{PluginScaffoldNaming.to_class_name(plugin_id)}() {{
  return request({{
    url: '/{plugin_id}/ping',
    method: 'get'
  }})
}}
"""

    @staticmethod
    def build_crud_api(plugin_id: str) -> str:
        """
        构建前端 CRUD API 模板内容。

        :param plugin_id: 插件ID
        :return: 前端 CRUD API 模板内容
        """
        class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""import request from '@/utils/request'

export function ping{class_name}() {{
  return request({{
    url: '/{plugin_id}/ping',
    method: 'get'
  }})
}}

export function list{class_name}Items(query) {{
  return request({{
    url: '/{plugin_id}/items',
    method: 'get',
    params: query
  }})
}}

export function add{class_name}Item(data) {{
  return request({{
    url: '/{plugin_id}/items',
    method: 'post',
    data
  }})
}}

export function update{class_name}Item(itemId, data) {{
  return request({{
    url: '/{plugin_id}/items/' + itemId,
    method: 'put',
    data
  }})
}}

export function del{class_name}Item(itemId) {{
  return request({{
    url: '/{plugin_id}/items/' + itemId,
    method: 'delete'
  }})
}}
"""

    @staticmethod
    def build_view(plugin_id: str) -> str:
        """
        构建前端视图模板内容。

        :param plugin_id: 插件ID
        :return: 前端视图模板内容
        """
        return f"""<template>
  <div class=\"app-container\">
    <el-card shadow=\"never\">
      <template #header>{plugin_id}</template>
      <div>{plugin_id} plugin</div>
    </el-card>
  </div>
</template>
"""

    @staticmethod
    def build_crud_view(plugin_id: str) -> str:
        """
        构建前端 CRUD 视图模板内容。

        :param plugin_id: 插件ID
        :return: 前端 CRUD 视图模板内容
        """
        class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""<template>
  <div class=\"app-container\">
    <el-form :model=\"queryParams\" :inline=\"true\">
      <el-form-item label=\"名称\">
        <el-input v-model=\"queryParams.keyword\" placeholder=\"请输入名称\" clearable />
      </el-form-item>
      <el-form-item>
        <el-button type=\"primary\" icon=\"Search\" @click=\"getList\">搜索</el-button>
        <el-button icon=\"Refresh\" @click=\"resetQuery\">重置</el-button>
        <el-button type=\"primary\" plain icon=\"Plus\" @click=\"handleAdd\">新增</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading=\"loading\" :data=\"itemList\" border>
      <el-table-column label=\"ID\" prop=\"itemId\" width=\"90\" align=\"center\" />
      <el-table-column label=\"名称\" prop=\"itemName\" min-width=\"180\" />
      <el-table-column label=\"状态\" prop=\"status\" width=\"90\" align=\"center\">
        <template #default=\"scope\">
          <el-tag :type=\"scope.row.status === '0' ? 'success' : 'info'\">{{{{ scope.row.status === '0' ? '正常' : '停用' }}}}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label=\"备注\" prop=\"remark\" min-width=\"220\" />
      <el-table-column label=\"操作\" width=\"150\" align=\"center\">
        <template #default=\"scope\">
          <el-button link type=\"primary\" icon=\"Edit\" @click=\"handleUpdate(scope.row)\">修改</el-button>
          <el-button link type=\"danger\" icon=\"Delete\" @click=\"handleDelete(scope.row)\">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title=\"dialogTitle\" v-model=\"open\" width=\"520px\" append-to-body>
      <el-form ref=\"itemRef\" :model=\"form\" :rules=\"rules\" label-width=\"90px\">
        <el-form-item label=\"名称\" prop=\"itemName\">
          <el-input v-model=\"form.itemName\" placeholder=\"请输入名称\" />
        </el-form-item>
        <el-form-item label=\"状态\" prop=\"status\">
          <el-radio-group v-model=\"form.status\">
            <el-radio label=\"0\">正常</el-radio>
            <el-radio label=\"1\">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label=\"备注\" prop=\"remark\">
          <el-input v-model=\"form.remark\" type=\"textarea\" :rows=\"3\" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class=\"dialog-footer\">
          <el-button type=\"primary\" @click=\"submitForm\">确 定</el-button>
          <el-button @click=\"open = false\">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name=\"{class_name}Plugin\">
import {{
  add{class_name}Item,
  del{class_name}Item,
  list{class_name}Items,
  update{class_name}Item
}} from '../api/{plugin_id}'

const {{ proxy }} = getCurrentInstance()

const loading = ref(false)
const open = ref(false)
const dialogTitle = ref('')
const itemList = ref([])
const queryParams = reactive({{
  keyword: ''
}})
const form = reactive({{
  itemId: undefined,
  itemName: '',
  status: '0',
  remark: ''
}})
const rules = {{
  itemName: [{{ required: true, message: '名称不能为空', trigger: 'blur' }}]
}}

function resetForm() {{
  form.itemId = undefined
  form.itemName = ''
  form.status = '0'
  form.remark = ''
}}

function getList() {{
  loading.value = true
  list{class_name}Items(queryParams).then(response => {{
    const data = response.data || response
    itemList.value = data.rows || []
  }}).finally(() => {{
    loading.value = false
  }})
}}

function resetQuery() {{
  queryParams.keyword = ''
  getList()
}}

function handleAdd() {{
  resetForm()
  dialogTitle.value = '新增{plugin_id}'
  open.value = true
}}

function handleUpdate(row) {{
  resetForm()
  form.itemId = row.itemId
  form.itemName = row.itemName
  form.status = row.status
  form.remark = row.remark
  dialogTitle.value = '修改{plugin_id}'
  open.value = true
}}

function submitForm() {{
  proxy.$refs.itemRef.validate(valid => {{
    if (!valid) {{
      return
    }}
    const request = form.itemId ? update{class_name}Item(form.itemId, form) : add{class_name}Item(form)
    request.then(() => {{
      proxy.$modal.msgSuccess('保存成功')
      open.value = false
      getList()
    }})
  }})
}}

function handleDelete(row) {{
  proxy.$modal.confirm('确认删除数据\"' + row.itemName + '\"吗?').then(function () {{
    return del{class_name}Item(row.itemId)
  }}).then(() => {{
    proxy.$modal.msgSuccess('删除成功')
    getList()
  }})
}}

getList()
</script>
"""

    @staticmethod
    def build_readme(plugin_id: str) -> str:
        """
        构建前端 README 内容。

        :param plugin_id: 插件ID
        :return: 前端 README 内容
        """
        return f"""# {plugin_id} frontend plugin

Frontend plugin scaffold generated by `ruoyi plugin create`.

## Structure

- `api/`: request wrappers used by plugin pages.
- `views/`: Vue pages loaded by backend menu component paths.
- `../../tests/plugins/{plugin_id}/`: frontend node tests for plugin view resolving.

## Route Component

The backend menu component `plugin/{plugin_id}/index` maps to:

```text
plugins/{plugin_id}/views/index.vue
```
"""

    @staticmethod
    def build_test(plugin_id: str) -> str:
        """
        构建前端插件 node 测试样例。

        :param plugin_id: 插件ID
        :return: 前端插件测试样例内容
        """
        return f"""import assert from 'node:assert/strict'
import {{ existsSync }} from 'node:fs'
import {{ dirname, resolve }} from 'node:path'
import {{ fileURLToPath }} from 'node:url'

import {{ resolvePluginViewPath }} from '../../../src/utils/pluginViewResolver.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const frontendRoot = resolve(__dirname, '../../..')
const viewPath = resolve(frontendRoot, 'plugins', '{plugin_id}', 'views', 'index.vue')

assert.equal(resolvePluginViewPath('plugin/{plugin_id}/index'), '../../../plugins/{plugin_id}/views/index.vue')
assert.equal(existsSync(viewPath), true)

console.log('{plugin_id} plugin frontend tests passed')
"""


class PluginFrontendScaffoldTemplateBuilder:
    """
    根据目标 Vue 版本分派前端插件模板。
    """

    @staticmethod
    def build_api(plugin_id: str) -> str:
        return PluginVue3FrontendScaffoldTemplateBuilder.build_api(plugin_id)

    @staticmethod
    def build_crud_api(plugin_id: str) -> str:
        return PluginVue3FrontendScaffoldTemplateBuilder.build_crud_api(plugin_id)

    @classmethod
    def build_view(cls, plugin_id: str, frontend_version: FrontendVersion = 'vue3') -> str:
        return cls._resolve_builder(frontend_version).build_view(plugin_id)

    @classmethod
    def build_crud_view(cls, plugin_id: str, frontend_version: FrontendVersion = 'vue3') -> str:
        return cls._resolve_builder(frontend_version).build_crud_view(plugin_id)

    @classmethod
    def build_readme(cls, plugin_id: str, frontend_version: FrontendVersion = 'vue3') -> str:
        return cls._resolve_builder(frontend_version).build_readme(plugin_id)

    @classmethod
    def build_test(cls, plugin_id: str, frontend_version: FrontendVersion = 'vue3') -> str:
        return cls._resolve_builder(frontend_version).build_test(plugin_id)

    @staticmethod
    def _resolve_builder(
        frontend_version: FrontendVersion,
    ) -> type[PluginVue2FrontendScaffoldTemplateBuilder] | type[PluginVue3FrontendScaffoldTemplateBuilder]:
        if frontend_version == 'vue2':
            return PluginVue2FrontendScaffoldTemplateBuilder
        if frontend_version == 'vue3':
            return PluginVue3FrontendScaffoldTemplateBuilder
        raise ValueError(f'不支持的 Vue 版本：{frontend_version}')
