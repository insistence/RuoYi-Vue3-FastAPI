# 文件管理使用与业务接入指南

本文说明文件管理功能怎么使用，以及业务模块怎么接入。

## 1. 怎么选择上传方式

| 场景 | 使用方式 | 业务保存内容 |
| --- | --- | --- |
| 头像、Logo、富文本图片等公开资源 | `/common/upload` 或 `ImageUpload` | `/profile/...` URL |
| 旧业务的普通公开附件 | 默认 `FileUpload` | URL 字符串 |
| 简单私有附件，不需要业务引用保护 | `FileUpload :is-private="true"` | 鉴权下载 URL |
| 合同、审批材料等正式业务附件 | `/common/files/upload` | `fileId` 列表 |

正式业务附件推荐使用最后一种方式，它支持：

- 文件下载鉴权。
- 用户、角色、部门 ACL。
- 业务引用保护，防止文件仍在使用时被删除。
- 按业务类型应用保留策略。
- 文件操作审计和回收站。

公开文件通过 `/profile` 直接访问，不适合存放需要权限保护的内容。

## 2. 文件管理页面怎么使用

文件管理页面主要用于：

- 查询文件、占用空间、所有者、所属部门和文件状态。
- 查看文件详情、业务引用和操作审计。
- 为私有文件授权用户、角色或部门下载。
- 转移文件所有者和所属部门。
- 将没有业务引用的文件移入回收站。
- 恢复文件或永久清理回收站文件。
- 配置业务保留策略和查看到期提醒。

文件管理操作同时受菜单权限和数据权限限制。部门管理员只能管理其文件数据范围内的文件。

私有文件下载规则可以简单理解为：

1. 文件到期后直接拒绝。
2. 管理员或文件所有者允许。
3. 命中的 `deny` ACL 优先拒绝。
4. 上传者允许。
5. 命中的 `allow` ACL 允许。
6. 其他情况默认拒绝。

## 3. 前端接入

### 3.1 通用约定

Vue2 和 Vue3 使用相同的受保护文件上传接口：

```http
POST /common/files/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>
```

上传成功后会返回：

```json
{
  "code": 200,
  "fileId": "8e5787b4-daf7-4e31-bf04-f1cc16e0f65a",
  "originalFilename": "合同.pdf",
  "accessType": "private",
  "downloadUrl": "/common/files/8e5787b4-daf7-4e31-bf04-f1cc16e0f65a/download/合同.pdf"
}
```

业务表单都应保存 `{ fileId, name, url }`，提交业务接口时传完整的 `fileId` 列表。不要从下载 URL 中截取 `fileId`。

### 3.2 Vue3 写法

Vue3 项目使用 Element Plus 和 Composition API：

```vue
<template>
  <div>
    <el-upload
      multiple
      :action="uploadUrl"
      :headers="headers"
      :file-list="attachmentList"
      :on-success="handleUploadSuccess"
      :show-file-list="false"
    >
      <el-button type="primary">选择附件</el-button>
    </el-upload>
    <el-link
      v-for="item in attachmentList"
      :key="item.fileId"
      @click.prevent="downloadAttachment(item)"
    >
      {{ item.name }}
    </el-link>
  </div>
</template>

<script setup>
import { getToken } from "@/utils/auth";

const { proxy } = getCurrentInstance();
const uploadUrl = `${import.meta.env.VITE_APP_BASE_API}/common/files/upload`;
const headers = { Authorization: `Bearer ${getToken()}` };
const attachmentList = ref([]);

function handleUploadSuccess(response, uploadFile) {
  if (response.code !== 200) {
    proxy.$modal.msgError(response.msg);
    return;
  }
  attachmentList.value.push({
    uid: uploadFile.uid,
    fileId: response.fileId,
    name: response.originalFilename,
    url: response.downloadUrl
  });
}

function buildSubmitData(form) {
  return {
    ...form,
    attachmentFileIds: attachmentList.value.map(item => item.fileId)
  };
}

function downloadAttachment(attachment) {
  proxy.$download.file(attachment.url);
}
</script>
```

### 3.3 Vue2 写法

Vue2 项目使用 Element UI、Options API 和 `process.env.VUE_APP_BASE_API`：

```vue
<template>
  <div>
    <el-upload
      multiple
      :action="uploadUrl"
      :headers="headers"
      :file-list="attachmentList"
      :on-success="handleUploadSuccess"
      :show-file-list="false"
    >
      <el-button size="mini" type="primary">选择附件</el-button>
    </el-upload>
    <el-link
      v-for="item in attachmentList"
      :key="item.fileId"
      @click.prevent="downloadAttachment(item)"
    >
      {{ item.name }}
    </el-link>
  </div>
</template>

<script>
import { getToken } from "@/utils/auth";

export default {
  name: "ContractAttachment",
  data() {
    return {
      uploadUrl: process.env.VUE_APP_BASE_API + "/common/files/upload",
      headers: {
        Authorization: "Bearer " + getToken()
      },
      attachmentList: []
    };
  },
  methods: {
    handleUploadSuccess(response, uploadFile) {
      if (response.code !== 200) {
        this.$modal.msgError(response.msg);
        return;
      }
      this.attachmentList.push({
        uid: uploadFile.uid,
        fileId: response.fileId,
        name: response.originalFilename,
        url: response.downloadUrl
      });
    },
    buildSubmitData(form) {
      return {
        ...form,
        attachmentFileIds: this.attachmentList.map(item => item.fileId)
      };
    },
    downloadAttachment(attachment) {
      this.$download.file(attachment.url);
    }
  }
};
</script>
```

### 3.4 现有上传组件的适用范围

Vue2 和 Vue3 都可以使用下面的写法上传简单私有附件：

```vue
<file-upload v-model="form.attachment" :is-private="true" />
```

两个版本的现有 `FileUpload` 都只把下载 URL 写入 `v-model`，不会保留 `fileId`。因此它们只适合旧业务或不需要引用保护的简单附件。正式业务附件应使用前述结构化写法，或分别封装 Vue2、Vue3 结构化上传组件。

封装复用组件时，Vue3 使用 `modelValue` 和 `update:modelValue`，Vue2 使用 `value` 和 `input` 事件。

两个版本的 `ImageUpload` 都继续用于公开图片。受保护文件下载应调用 `$download.file()`，不要使用普通 `<a>` 标签直接打开。

## 4. 后端业务接入

下面以“合同”业务为例。

### 4.1 定义业务类型

每个业务模块定义一个稳定的业务类型：

```python
CONTRACT_FILE_BUSINESS_TYPE = 'contract'
```

该值用于关联业务引用和保留策略。上线后不要随意修改，也不要使用中文显示名称。

### 4.2 请求模型接收文件 ID

```python
class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    contract_id: int | None = Field(default=None, description='合同ID')
    contract_name: str = Field(description='合同名称')
    attachment_file_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
        description='附件文件ID列表',
    )
```

修改接口必须传“修改后需要保留的完整文件 ID 列表”，空列表表示移除全部附件。

### 4.3 注入文件数据权限

业务控制器需要注入文件数据权限，并传给业务 Service：

```python
file_data_scope_sql: Annotated[
    ColumnElement,
    DataScopeDependency(
        SysFileInfo,
        user_alias='owner_user_id',
        dept_alias='dept_id',
    ),
]
```

引用服务会校验文件存在、状态正常，并且位于当前用户的文件数据范围内。

### 4.4 新增和修改时同步引用

新增业务记录取得业务 ID 后，在同一个事务中写入文件引用：

```python
try:
    db_contract = await ContractDao.add_contract_dao(query_db, contract)
    await FileReferenceService.replace_business_file_references_services(
        query_db=query_db,
        business_type=CONTRACT_FILE_BUSINESS_TYPE,
        business_id=str(db_contract.contract_id),
        file_ids=contract.attachment_file_ids,
        create_by=current_user.user.user_name,
        file_data_scope_sql=file_data_scope_sql,
        business_name=contract.contract_name,
    )
    await query_db.commit()
except Exception:
    await query_db.rollback()
    raise
```

修改业务时调用同一个方法，传入修改后的完整列表：

```python
await ContractDao.edit_contract_dao(query_db, contract)
await FileReferenceService.replace_business_file_references_services(
    query_db=query_db,
    business_type=CONTRACT_FILE_BUSINESS_TYPE,
    business_id=str(contract.contract_id),
    file_ids=contract.attachment_file_ids,
    create_by=current_user.user.user_name,
    file_data_scope_sql=file_data_scope_sql,
    business_name=contract.contract_name,
)
await query_db.commit()
```

`replace_business_file_references_services` 是全量替换：

- 原来是 `[A, B]`，现在传 `[B, C]`：解除 A，保留 B，新增 C。
- 传空列表：解除该业务对象的全部引用。

业务 DAO 应使用 `flush()` 获取新增 ID，不要提前 `commit()`。业务数据和文件引用必须由业务 Service 统一提交或回滚。

### 4.5 删除业务时解除引用

先用业务模块自身的数据权限确认业务对象可以删除，再在同一事务中解除引用：

```python
try:
    db_contract = await ContractDao.get_contract_by_id_for_update(
        query_db,
        contract_id,
        contract_data_scope_sql,
    )
    if db_contract is None:
        raise ServiceException(message='合同不存在或超出数据权限')

    await FileReferenceService.remove_business_file_references_services(
        query_db,
        CONTRACT_FILE_BUSINESS_TYPE,
        str(contract_id),
    )
    await ContractDao.delete_contract_dao(query_db, contract_id)
    await query_db.commit()
except Exception:
    await query_db.rollback()
    raise
```

`remove_business_file_references_services` 不负责校验合同权限，所以必须在业务模块完成鉴权后调用。

解除引用不会立即删除文件。没有其他业务引用后，文件管理员才能将文件移入回收站。

### 4.6 业务详情回显附件

业务详情接口应按以下条件查询 `sys_file_reference` 并关联 `sys_file_info`：

```text
business_type = CONTRACT_FILE_BUSINESS_TYPE
business_id = str(contract_id)
```

建议返回：

```json
{
  "fileId": "8e5787b4-daf7-4e31-bf04-f1cc16e0f65a",
  "name": "合同.pdf",
  "downloadUrl": "/common/files/8e5787b4-daf7-4e31-bf04-f1cc16e0f65a/download/合同.pdf"
}
```

不要向前端返回 `storage_key`、物理路径或私有目录信息。

## 5. 业务引用、下载权限和保留策略

这三项作用不同：

| 能力 | 作用 |
| --- | --- |
| 业务引用 | 记录文件正在被哪个业务使用，并阻止误删 |
| 文件 ACL | 决定除所有者、上传者外，还有谁可以下载 |
| 保留策略 | 决定新业务引用什么时候到期 |

业务引用不会自动授予下载权限。其他能查看合同的用户如果也要下载附件，需要：

- 在文件管理页面手工配置用户、角色或部门 ACL；或
- 由业务模块在参与人、角色、部门变化时同步文件 ACL。

保留策略按 `business_type` 生效，不是在文件上直接选择策略。例如：

```text
保留策略：business_type=contract，retention_days=365
业务引用：business_type=contract，business_id=1001
结果：该引用在创建时得到 365 天的保留期限
```

因此，只有合同模块实际调用引用服务，并传入相同的 `business_type='contract'`，策略才会作用到附件。

还需要注意：

- 策略只应用于新建或重新写入的引用，不会自动修改历史引用。
- 配置保留策略的业务只能引用私有文件。
- 到期后文件不能下载，但不会自动删除，也不会自动解除引用。
- 一个文件有多个引用时，只要存在永久引用，文件就不会到期。

## 6. 接入检查

一个业务模块完成以下内容即视为接入完成：

- [ ] 使用 `/common/files/upload` 上传正式业务附件。
- [ ] 前端保存上传响应中的 `fileId`。
- [ ] 新增和修改接口传递完整的文件 ID 列表。
- [ ] 控制器注入文件数据权限。
- [ ] 业务新增、修改与引用更新使用同一个事务。
- [ ] 业务删除先鉴权，再在同一事务中解除引用。
- [ ] 业务详情返回结构化附件和鉴权下载地址。
- [ ] 明确非所有者用户通过什么 ACL 下载。
- [ ] 如果配置保留策略，策略的 `business_type` 与代码常量一致。

完成这些步骤后，文件管理页面才能正确显示业务引用，删除保护和保留策略也才会真正生效。
