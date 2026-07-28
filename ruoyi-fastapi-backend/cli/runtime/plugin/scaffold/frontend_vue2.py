from .naming import PluginScaffoldNaming


class PluginVue2FrontendScaffoldTemplateBuilder:
    """
    Vue 2 前端插件模板内容构建器。
    """

    @staticmethod
    def build_view(plugin_id: str) -> str:
        """
        构建 Vue 2 前端视图模板内容。

        :param plugin_id: 插件ID
        :return: 前端视图模板内容
        """
        return f"""<template>
  <div class=\"app-container\">
    <el-card shadow=\"never\">
      <div slot=\"header\">{plugin_id}</div>
      <div>{plugin_id} plugin</div>
    </el-card>
  </div>
</template>
"""

    @staticmethod
    def build_crud_view(plugin_id: str) -> str:
        """
        构建 Vue 2 前端 CRUD 视图模板内容。

        :param plugin_id: 插件ID
        :return: 前端 CRUD 视图模板内容
        """
        class_name = PluginScaffoldNaming.to_class_name(plugin_id)
        return f"""<template>
  <div class=\"app-container\">
    <el-form ref=\"queryForm\" :model=\"queryParams\" size=\"small\" :inline=\"true\">
      <el-form-item label=\"名称\">
        <el-input v-model=\"queryParams.keyword\" placeholder=\"请输入名称\" clearable />
      </el-form-item>
      <el-form-item>
        <el-button type=\"primary\" icon=\"el-icon-search\" size=\"mini\" @click=\"getList\">搜索</el-button>
        <el-button icon=\"el-icon-refresh\" size=\"mini\" @click=\"resetQuery\">重置</el-button>
        <el-button type=\"primary\" plain icon=\"el-icon-plus\" size=\"mini\" @click=\"handleAdd\">新增</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading=\"loading\" :data=\"itemList\" border>
      <el-table-column label=\"ID\" prop=\"itemId\" width=\"90\" align=\"center\" />
      <el-table-column label=\"名称\" prop=\"itemName\" min-width=\"180\" />
      <el-table-column label=\"状态\" prop=\"status\" width=\"90\" align=\"center\">
        <template slot-scope=\"scope\">
          <el-tag :type=\"scope.row.status === '0' ? 'success' : 'info'\">{{{{ scope.row.status === '0' ? '正常' : '停用' }}}}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label=\"备注\" prop=\"remark\" min-width=\"220\" />
      <el-table-column label=\"操作\" width=\"150\" align=\"center\">
        <template slot-scope=\"scope\">
          <el-button type=\"text\" icon=\"el-icon-edit\" size=\"mini\" @click=\"handleUpdate(scope.row)\">修改</el-button>
          <el-button type=\"text\" icon=\"el-icon-delete\" size=\"mini\" @click=\"handleDelete(scope.row)\">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title=\"dialogTitle\" :visible.sync=\"open\" width=\"520px\" append-to-body>
      <el-form ref=\"itemForm\" :model=\"form\" :rules=\"rules\" label-width=\"90px\">
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
      <div slot=\"footer\" class=\"dialog-footer\">
        <el-button type=\"primary\" @click=\"submitForm\">确 定</el-button>
        <el-button @click=\"open = false\">取 消</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {{
  add{class_name}Item,
  del{class_name}Item,
  list{class_name}Items,
  update{class_name}Item
}} from '../api/{plugin_id}'

export default {{
  name: '{class_name}Plugin',
  data() {{
    return {{
      loading: false,
      open: false,
      dialogTitle: '',
      itemList: [],
      queryParams: {{
        keyword: ''
      }},
      form: {{
        itemId: undefined,
        itemName: '',
        status: '0',
        remark: ''
      }},
      rules: {{
        itemName: [{{ required: true, message: '名称不能为空', trigger: 'blur' }}]
      }}
    }}
  }},
  created() {{
    this.getList()
  }},
  methods: {{
    resetFormData() {{
      this.form = {{
        itemId: undefined,
        itemName: '',
        status: '0',
        remark: ''
      }}
    }},
    getList() {{
      this.loading = true
      list{class_name}Items(this.queryParams).then(response => {{
        const data = response.data || response
        this.itemList = data.rows || []
      }}).finally(() => {{
        this.loading = false
      }})
    }},
    resetQuery() {{
      this.queryParams.keyword = ''
      this.getList()
    }},
    handleAdd() {{
      this.resetFormData()
      this.dialogTitle = '新增{plugin_id}'
      this.open = true
    }},
    handleUpdate(row) {{
      this.resetFormData()
      this.form = {{
        itemId: row.itemId,
        itemName: row.itemName,
        status: row.status,
        remark: row.remark
      }}
      this.dialogTitle = '修改{plugin_id}'
      this.open = true
    }},
    submitForm() {{
      this.$refs.itemForm.validate(valid => {{
        if (!valid) {{
          return
        }}
        const request = this.form.itemId
          ? update{class_name}Item(this.form.itemId, this.form)
          : add{class_name}Item(this.form)
        request.then(() => {{
          this.$modal.msgSuccess('保存成功')
          this.open = false
          this.getList()
        }})
      }})
    }},
    handleDelete(row) {{
      this.$modal.confirm('确认删除数据\"' + row.itemName + '\"吗?').then(function () {{
        return del{class_name}Item(row.itemId)
      }}).then(() => {{
        this.$modal.msgSuccess('删除成功')
        this.getList()
      }})
    }}
  }}
}}
</script>
"""

    @staticmethod
    def build_readme(plugin_id: str) -> str:
        """
        构建 Vue 2 前端 README 内容。

        :param plugin_id: 插件ID
        :return: 前端 README 内容
        """
        return f"""# {plugin_id} frontend plugin

Vue 2 frontend plugin scaffold generated by `ruoyi plugin create`.

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
        构建 Vue 2 前端插件 node 测试样例。

        :param plugin_id: 插件ID
        :return: 前端插件测试样例内容
        """
        return f"""const assert = require('assert').strict
const {{ existsSync }} = require('fs')
const {{ resolve }} = require('path')
const {{ resolvePluginViewPath }} = require('../../../src/utils/pluginViewResolver')

const frontendRoot = resolve(__dirname, '../../..')
const viewPath = resolve(frontendRoot, 'plugins', '{plugin_id}', 'views', 'index.vue')

assert.equal(resolvePluginViewPath('plugin/{plugin_id}/index'), './{plugin_id}/views/index.vue')
assert.equal(existsSync(viewPath), true)

console.log('{plugin_id} plugin frontend tests passed')
"""
