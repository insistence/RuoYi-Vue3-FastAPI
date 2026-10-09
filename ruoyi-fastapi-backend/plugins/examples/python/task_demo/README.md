# 持久化任务示例

`task_demo` 是 manifest v2 的 Python ASGI + 独立 bundle 业务示例，当前版本 `1.1.0`。页面提供新增、编辑、删除、状态筛选和分页；数据保存在宿主默认数据源的 `ruoyi_plugin_task_demo` 表中。它演示插件级共享任务清单：有查看权限的用户看到同一组任务，未实现个人、部门或租户数据隔离。

源码位于 `plugins/examples/python/task_demo`，示例目录不参与运行时插件扫描。下面的命令均在后端根目录、已激活并安装宿主依赖的 Python 3.10–3.13 环境执行，适用于 Windows PowerShell、macOS 和 Linux；前端构建使用 Node.js 22。

## 构建与测试

```bash
npm --prefix plugins/examples/python/task_demo/web install --no-audit --no-fund --package-lock=false
npm --prefix plugins/examples/python/task_demo/web test
npm --prefix plugins/examples/python/task_demo/web run build
python plugins/examples/python/task_demo/build_release.py --output target/task-demo-1.1.0
python -m pytest tests/plugins/examples/test_task_demo.py tests/plugins/core/deployment/test_task_delivery.py -q
```

每次使用不存在的新输出目录。交付和签名输入为 `target/task-demo-1.1.0/task_demo`，包含清单、三个 Python 业务模块、MySQL/PostgreSQL 各两份 SQL 和 `web/dist`；不包含开发页面、测试、依赖目录、构建脚本或文件清单。Python 后端仍以源码交付。

`release-files.json` 使用 `schemaVersion: 1` 和显式 `files` 数组列出业务 `.py`、`.sql` 文件；`plugin.yaml` 和已构建的 `web/dist` 自动纳入。新增模块或迁移时同时更新这份清单与 `plugin.yaml` 中的相应声明。构建器不展开通配符、不递归收集 Python 源码，不导入插件、不执行 npm，也不生成签名；缺失文件、非法路径、链接和开发资源会在建立输出目录前被拒绝。旧工程可保留已有构建器；该清单是当前生成脚本的输入，不会自动升级旧脚本。

示例前端通过 Vite 别名引用同一仓库的宿主桥接 SDK。需要把示例移到独立仓库时，按[脚手架与 SDK 溯源说明](../../../../docs/plugin_development.md#161-桥接-sdk-溯源与显式更新)使用 `python-bundle` 工程的 `web/vendor` 及构建配置，再迁入业务代码。

## 本地页面开发

```bash
npm --prefix plugins/examples/python/task_demo/web run dev
```

打开开发服务的 `/dev.html`，可预览任务清单、主题、只读状态和失败反馈。开发宿主使用内存数据，刷新页面会重置，不能验证真实数据库事务或宿主权限。生产构建只包含业务页面，不包含此开发宿主；正式访问应从宿主菜单打开 `PluginFrame`。

## 安装与权限

开发环境可将构建出的 `task_demo` 目录复制到后端 `plugins/task_demo`，然后执行：

```bash
ruoyi plugin check task_demo --env=dev
ruoyi plugin install task_demo --env=dev --yes
ruoyi plugin enable task_demo --env=dev --yes
```

重启后端后，为角色授予 `task_demo:view`，重新获取菜单即可查看任务；需要增删改时另授予 `task_demo:write`。页面根据接口返回的 `canWrite` 显示只读状态，每个业务接口仍独立校验权限。写权限不隐含查看权限，完整页面操作应授予两者。

首次引入 bundle 支持时需构建包含 `PluginFrame` 的宿主前端；之后更新此插件只需重建插件页面。子页面通过 `createPluginClient` 调用自身 API，无独立登录，不读取或传递管理员 token。JSON 请求遵循宿主的插件会话、CSRF 和传输加密策略，无需为本示例增加加密例外。

## 接口与事务

以下路径相对于 `/apps/task_demo/api`。桥接 SDK 中使用 `path: 'tasks'`，查询字段使用 `params`。

| 方法与路径 | 权限 | 返回或行为 |
| --- | --- | --- |
| `GET /info` | `task_demo:view` | 插件版本与 `canWrite` |
| `GET /tasks` | `task_demo:view` | `items/total/page/pageSize/canWrite`；支持 `status=todo/done` |
| `GET /tasks/{id}` | `task_demo:view` | 单条任务，不存在返回 404 |
| `POST /tasks` | `task_demo:write` | 新建任务，返回保存后的任务 |
| `PUT /tasks/{id}` | `task_demo:write` | 替换可编辑字段，返回保存后的任务 |
| `DELETE /tasks/{id}` | `task_demo:write` | 删除任务，返回 `deleted: true` |

请求体包含 `title`（必填、去除两端空白后非空、最长 120 字符）、`description`（默认空、最长 500 字符）、`status`（默认 `todo`，可选 `done`）和 `priority`（默认 `normal`，可选 `high`）。PUT 同样要求标题，未提供的可选字段使用默认值。未知字段和非法输入返回 422，无权限返回 403。ID 由服务器生成；响应时间使用固定毫秒精度的 UTC RFC3339 字符串。数据库列遵循宿主时间规范：MySQL `DATETIME(3)`、PostgreSQL `TIMESTAMP(3) WITH TIME ZONE`，Python 使用公共 `DbUtcDateTime` 类型完成 UTC 转换。

分页默认每页 10 条，最多 20 条；字段长度与页大小共同限制 JSON 体积，适配桥接的 64 KiB 消息上限。列表使用稳定排序。所有读写通过 `context.transaction()` 取得独立会话，成功退出提交，异常或取消回滚；不复用宿主鉴权会话，不访问宿主业务 DAO，不在启动或请求中自动建表。修改采取后写覆盖，不提供版本冲突检测；需要并发协同编辑时应扩展版本字段和冲突处理。

## 迁移与升级

| 版本 | 迁移 | 数据变化 |
| --- | --- | --- |
| `1.0.0` 数据结构 | `001_init.sql` | 建立任务表 |
| `1.1.0` | `002_priority.sql` | 增加 `priority`，既有行默认 `normal` |

清单同时列出两种数据库的脚本，宿主根据默认数据源类型选择本次方言，按声明顺序运行。首次安装执行两次迁移；从已安装的 1.0 数据结构升级仅执行 002，成功迁移的校验值与历史用于防止重复执行。不要修改已经执行过的 001；后续变更应新增文件并提高插件版本。

002 使用 `ALTER TABLE ADD COLUMN`，依靠宿主迁移历史实现只执行一次，不能脱离历史反复手工执行。MySQL DDL 可能隐式提交；中断后应按[迁移恢复手册](../../../../docs/plugin_migration_failure_runbook.md)确认实际结构和历史状态，不能假定失败自动恢复旧结构。代码回滚不撤销数据库迁移。

本地测试执行真实 SQLite SQL 和事务，覆盖 CRUD、读写权限、分页、校验、回滚以及旧行保留；将 SQLite 不支持的 PostgreSQL 时间类型替换为 `DATETIME`，迁移文件与校验值保持原样。交付测试从源码构建目录、签名、导入、维护准备及选择目标，再从签名制品加载当前业务代码。SQLite 仅允许单个写事务，因此本地交付夹具的宿主维护会话使用自动提交，并适配宿主菜单自增主键，业务 CRUD 仍用正常事务；它不验证宿主维护事务的数据库原子性。其 1.0 包是仅用于迁移验收的结构夹具，不提供历史页面或历史业务 API；页面资源在本地交付测试中是最小 HTML 夹具。真实数据库 CI 使用原始 SQL 和正常宿主事务，不进行以上适配。

真实 MySQL/PostgreSQL 交付验收接入 `scripts/plugin_release_integration.py` 和发布集成 CI：先构建本示例页面，再使用隔离数据库和 Redis 执行相同维护流程，验证旧行保留、当前 CRUD 和只读拒绝。它注入已认证请求上下文，通过 ASGI HTTP 适配器访问业务 API；真实浏览器登录、Cookie/CSRF/TLS 由独立网络 smoke 覆盖。配置工作流不等于已通过远端 CI，应查看对应提交的实际运行结果。

## 签名制品与维护发布

先按[签名交付手册](../../../../docs/plugin_development.md#15-v2-签名制品与维护发布)启用制品功能，配置外部信任公钥并授权 `task_demo`。签名私钥应位于源码和交付目录之外，以下路径为示例：

```bash
ruoyi plugin artifact build target/task-demo-1.1.0/task_demo target/task_demo-1.1.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher --env=dev --output=json
ruoyi plugin artifact verify target/task_demo-1.1.0.rpk --env=prod --output=json
ruoyi plugin artifact import target/task_demo-1.1.0.rpk --env=prod --allow-prod --yes --output=json
ruoyi plugin release plan task_demo DIGEST --env=prod --output=json
```

`DIGEST` 替换为实际导入结果。停止全部宿主 worker，在独立维护进程完成准备，然后读取最新 generation 并选择目标：

```bash
ruoyi plugin release prepare task_demo DIGEST --maintenance --env=prod --allow-prod --yes --output=json
ruoyi plugin release status --plugin-id task_demo --env=prod --output=json
ruoyi plugin release select task_demo DIGEST --expected-generation GENERATION --expected-workers 1 --maintenance --env=prod --allow-prod --yes --output=json
```

`GENERATION` 使用准备后最新 status 中的值，worker 数按实际部署调整。首装需确认启用状态；升级保留已有开关，不会自动启用已停用插件。启用操作及其代际要求见发布手册。重启全部 worker 后检查实际目标、健康状态及业务数据，不能以选择目标成功代替运行验收。

同名 `plugins/task_demo` 目录不能与签名制品共存；维护时先备份并移出目录插件。不可变制品只保存程序与静态资源，业务数据始终保存在数据库。健康检查验证包含新增优先级字段的任务表可读，缺表或缺列不会被报告为健康。
