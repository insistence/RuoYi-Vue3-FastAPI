# ASGI 子应用示例

本示例验证 v2 显式入口、子应用挂载、宿主 Bearer 认证、请求权限及 lifespan。它只提供 API；需要已接入的 PluginFrame、独立打包页面与浏览器会话桥时，参见 [bundle_demo](../bundle_demo/README.md)。

清单、入口与 SDK 约定见[插件开发手册](../../../../docs/plugin_development.md#510-v2-清单与能力组合)，资源初始化和关闭方式见[ASGI 生命周期说明](../../../../docs/plugin_development.md#67-asgi-子应用与生命周期)。

以下命令在后端目录执行，适用于 Windows PowerShell、macOS 和 Linux。先按 [CLI 环境准备](../../../../docs/cli_usage.md#22-安装依赖)激活已安装宿主依赖的 Python 环境。

1. 将此目录复制到后端 `plugins/asgi_demo`。
2. 在已激活的 Python 环境中执行 `ruoyi plugin check asgi_demo --env=dev`。
3. 使用现有安装与启用命令执行 `ruoyi plugin install asgi_demo --env=dev --yes` 和 `ruoyi plugin enable asgi_demo --env=dev --yes`。
4. 重启后端。按原有角色权限管理授予 `asgi_demo:view`；管理员具有通配权限。
5. 请求 `GET /apps/asgi_demo/api/info`，携带当前宿主登录的 `Authorization: Bearer <token>`。若启用了传输加密，仍需遵守宿主加密协议。

入口函数快速返回 PluginDefinition，资源在 lifespan 中初始化和关闭。API 从 request.state.plugin_context 获取宿主鉴权后的身份，执行具体权限检查。数据库会话通过 host.session_factory 按请求创建，不在应用实例内保存请求会话。

服务模式仍执行既有生命周期写入限制；示例命令用于开发环境，不应将生产配置切到 dev 以绕过限制。生产变更使用维护部署流程。当前没有热挂载或热卸载。

## 签名制品交付

本例是 Python 源码插件，签名不改变源码交付方式。使用[开发手册第 15 节](../../../../docs/plugin_development.md#15-v2-签名制品与维护发布)配置宿主制品存储和外部发布者公钥，并授权 `asgi_demo`。发布者私钥必须在插件目录之外，以下路径需替换为实际的 Ed25519 PKCS8 PEM：

```bash
ruoyi plugin artifact build plugins/examples/python/asgi_demo target/asgi_demo-1.0.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher --env=dev --output=json
ruoyi plugin artifact verify target/asgi_demo-1.0.0.rpk --env=prod --output=json
ruoyi plugin artifact import target/asgi_demo-1.0.0.rpk --env=prod --allow-prod --yes --output=json
```

导入只验签、检查并登记不可变目录，不加载子应用、不运行迁移或 Hook。选择制品部署时不能同时保留 `plugins/asgi_demo` 源码目录；如已按上面的开发步骤安装过，需在维护窗口处理目录冲突，并为缺少制品准备证据的既有安装提升版本。

后续严格使用导入返回的 digest，停止全部 worker 后执行 `release prepare`，从最新状态读取 generation，再执行 `release select` 并重启。每个 worker 分别启动 lifespan，只有实际报告匹配目标并就绪才算发布完成。生产操作不支持热挂载/卸载；代码回滚也不降级数据库。完整命令与当前签名撤销、相同内容重签限制均见开发手册。
