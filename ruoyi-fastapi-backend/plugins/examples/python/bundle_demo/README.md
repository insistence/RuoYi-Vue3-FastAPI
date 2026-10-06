# 独立打包前端插件示例

本示例使用 **Python ASGI 后端 + 独立 Vite 前端 bundle**。页面通过宿主 `PluginFrame` 打开，取得宿主主题、语言、时区和路由状态，再经受限 JSON 桥调用本插件的查询与回显 API。示例不会写业务数据库。

通用清单与后端入口见[插件开发手册](../../../../docs/plugin_development.md#510-v2-清单与能力组合)，浏览器集成协议见[bundle 页面与 SDK](../../../../docs/plugin_development.md#72-v2-独立-bundle-页面)。

前端交付 `web/dist`，不要求把插件页面加入宿主 Vue 源码或重新构建宿主。后端 `__init__.py` 仍是可读 Python 业务源码；需要保护后端源码时使用 [Rust 原生示例](../../rust/rust_demo/README.md)，并按 `native + asgi + bundle` 组合交付。编译前端也不保证浏览器端逻辑不可逆向。

## 构建前端

以下命令从仓库的 `ruoyi-fastapi-backend` 目录执行。Python 命令使用已安装宿主依赖的环境，准备步骤见 [CLI 环境准备](../../../../docs/cli_usage.md#22-安装依赖)。通用命令适用于 Windows PowerShell、macOS 和 Linux；Shell 语法不同的操作分别列出。构建端需已安装 Node.js/npm；部署端只使用构建产物，无需 Node.js。示例使用独立 `package.json`，不会把构建依赖写入宿主前端。

```bash
npm --prefix plugins/examples/python/bundle_demo/web install
npm --prefix plugins/examples/python/bundle_demo/web run build
```

首次安装会生成此示例自己的锁文件；独立维护插件时应保留锁文件，在 CI 中使用 `npm ci`。示例的 SDK 别名指向本仓库 `ruoyi-fastapi-frontend/src/utils/pluginBridge.js`。迁移到独立插件仓库时，把该无依赖模块复制为自己的版本化源码依赖，并调整 `vite.config.js` 中 `@ruoyi/plugin-bridge` 的别名。

如果本仓库宿主前端依赖已安装，也可复用其中的 Vite 可执行文件构建**同一个插件前端项目**：

```bash
node ../ruoyi-fastapi-frontend/node_modules/vite/bin/vite.js build plugins/examples/python/bundle_demo/web --config plugins/examples/python/bundle_demo/web/vite.config.js
```

两种方式均输出 `plugins/examples/python/bundle_demo/web/dist`。配置使用 `base: './'`、关闭 sourcemap；宿主交付 HTML 时注入有效 `<base>` 和运行基址，因此资源和页面深层链接不需写死域名或代理前缀。直接用 `file://` 打开 dist 或只启动插件 Vite 页面不会建立宿主身份桥；完整交互应从管理平台的插件菜单进入。

## 离线目录包

构建完成后，只打包清单、Python 后端文件和前端构建产物。选择当前平台对应的命令创建新目录；两种写法均在输出已存在时停止，避免覆盖已有发布包。

Windows PowerShell：

```powershell
$bundleSource = (Resolve-Path 'plugins/examples/python/bundle_demo').Path
$bundleDist = Join-Path $bundleSource 'web/dist'
if (-not (Test-Path -LiteralPath (Join-Path $bundleDist 'index.html'))) {
    throw '请先构建 bundle_demo 前端'
}
$bundleRelease = Join-Path (Get-Location).Path 'target/bundle-demo-1.0.0'
if (Test-Path -LiteralPath $bundleRelease) {
    throw '输出目录已存在，请选择新的发布目录'
}
$bundlePackage = Join-Path $bundleRelease 'bundle_demo'
New-Item -ItemType Directory -Path (Join-Path $bundlePackage 'web') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $bundleSource 'plugin.yaml') -Destination $bundlePackage
Copy-Item -LiteralPath (Join-Path $bundleSource '__init__.py') -Destination $bundlePackage
Copy-Item -LiteralPath $bundleDist -Destination (Join-Path $bundlePackage 'web') -Recurse
Compress-Archive -LiteralPath $bundlePackage -DestinationPath (Join-Path $bundleRelease 'bundle_demo-1.0.0.zip')
```

macOS / Linux（Bash、Zsh）：

```bash
(
    set -eu
    bundleSource='plugins/examples/python/bundle_demo'
    bundleDist="$bundleSource/web/dist"
    if [ ! -f "$bundleDist/index.html" ]; then
        printf '%s\n' '请先构建 bundle_demo 前端' >&2
        exit 1
    fi
    bundleRelease='target/bundle-demo-1.0.0'
    if [ -e "$bundleRelease" ]; then
        printf '%s\n' '输出目录已存在，请选择新的发布目录' >&2
        exit 1
    fi
    mkdir -p target
    mkdir "$bundleRelease"
    bundlePackage="$bundleRelease/bundle_demo"
    mkdir -p "$bundlePackage/web"
    cp "$bundleSource/plugin.yaml" "$bundleSource/__init__.py" "$bundlePackage/"
    cp -R "$bundleDist" "$bundlePackage/web/dist"
    python -m zipfile -c "$bundleRelease/bundle_demo-1.0.0.zip" "$bundlePackage"
)
```

ZIP 内布局：

```text
bundle_demo/
  plugin.yaml
  __init__.py
  web/
    dist/
      index.html
      assets/...
```

包不包含 `web/src`、`node_modules`、Vite 配置或 npm 清单。这里的普通 ZIP 供开发环境复制部署，不是签名 `.rpk`；生产维护发布应继续对准备好的 `bundle_demo` 目录签名，不能直接把这个 ZIP 当作已验签制品。

## 签名制品与维护发布

先按[开发手册第 15 节](../../../../docs/plugin_development.md#15-v2-签名制品与维护发布)配置宿主制品功能及外部发布者信任文件，并授权 `bundle_demo`。发布者准备位于插件目录之外的 Ed25519 PKCS8 PEM 私钥，再执行：

```bash
ruoyi plugin artifact build target/bundle-demo-1.0.0/bundle_demo target/bundle_demo-1.0.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher --env=dev --output=json
ruoyi plugin artifact verify target/bundle_demo-1.0.0.rpk --env=prod --output=json
ruoyi plugin artifact import target/bundle_demo-1.0.0.rpk --env=prod --allow-prod --yes --output=json
```

签名私钥路径仅作示例；包内公钥不能自行建立信任。输入为已经剔除前端工程的部署目录，不能直接传入包含 `web/src`、`package.json` 或 `node_modules` 的开发目录。本例 Python 后端仍以源码交付，前端以 `web/dist` 交付，签名并不加密这些文件。

导入成功后，制品保存在 `<store>/bundle_demo/<version>/<digest>/payload/bundle_demo`；验签、现有文件复验和发布者授权按当前宿主信任配置执行。与 `plugins/bundle_demo` 源码目录不能共存，导入也不等于安装或激活。继续使用返回的精确 digest 查看发布计划，停止全部 worker 后准备迁移/Hook，读取最新 generation 并选择目标，最后启动全部 worker 检查状态。相同版本缺少匹配 digest 的准备证据时应提升版本，不允许猜测已安装内容。

制品目录保持不可变；页面资源、入口、Python 模块及签名均不能原位替换。代码回滚要求旧代码兼容现有数据结构，不会回退数据库。相同内容重签不改变 digest，也不覆盖已有签名；旧签名撤销后需要新内容或显式维护清理。当前没有热卸载、自动停止 worker 或自动制品清理命令。完整流程和故障处理见开发手册。

## 在开发环境安装

1. 首次升级宿主时，构建包含 `PluginFrame` 的宿主前端；后续新增或更新此 bundle 不需要重建宿主。
2. 将交付目录中的 `bundle_demo` 复制到后端 `plugins/bundle_demo`，确保 `web/dist/index.html` 已存在。不要把整个开发源码目录当成交付要求。
3. 在已激活并安装宿主依赖的 Python 环境、后端目录执行（三种平台通用）：

   ```bash
   ruoyi plugin check bundle_demo --env=dev
   ruoyi plugin install bundle_demo --env=dev --yes
   ruoyi plugin enable bundle_demo --env=dev --yes
   ```

4. 重启后端；在现有角色权限管理中授予 `bundle_demo:view`，或使用具有通配权限的管理员。
5. 重新取得用户菜单后打开“独立前端示例”。页面会显示实际登录用户、服务端时间，并支持有权限的 POST 回显。

`plugin.yaml` 使用 Host API `^1.2.0`。菜单组件为 `PluginFrame`，后端根据 `sys_plugin_menu` 的真实关联返回 `meta.pluginId`；不从路径或 `query.pluginId` 推测插件。只有已启用、已激活且用户有权限的 bundle 可以签发浏览器会话。

生产模式继续遵守现有生命周期写操作限制，应通过维护部署流程更新并重启。不要把生产配置切到 dev 来绕过限制，也不要期待复制目录后自动热挂载。

## 浏览器 SDK

实际用例见 [web/src/main.js](web/src/main.js)。`createPluginClient` 只在同源宿主 iframe 中使用，初始化配置由宿主注入：

```javascript
import { createPluginClient } from '@ruoyi/plugin-bridge'

const config = JSON.parse(document.getElementById('ruoyi-plugin-config').textContent)
const client = createPluginClient({ pluginId: config.pluginId })
const context = await client.ready
// context 包含 theme、language、timeZone、route、uiBase、apiBase。

const summary = await client.request({ method: 'GET', path: 'summary' })
const echo = await client.request({
  method: 'POST',
  path: 'echo',
  data: { message: `你好，${summary.userName}` },
})
console.log(echo.message)

const unsubscribe = client.subscribe(({ type, payload }) => {
  if (type === 'preferences') applyPreferences(payload)
  if (type === 'route') showPage(payload.route)
  if (type === 'refresh') refreshData()
  if (type === 'logout') showLoggedOut()
})
client.navigate('/details')

window.addEventListener('pagehide', () => {
  unsubscribe()
  client.destroy()
}, { once: true })
```

`applyPreferences`、`showPage`、`refreshData`、`showLoggedOut` 由插件实现。路由通知只更新插件页面状态；示例将 `/details` 同步到宿主 `pluginRoute` 查询参数，并由订阅回调切换内容。

`request` 的 `path` 必须相对于本插件 `apiBase`，例如 `summary`、`reports/month`；不能是完整 URL、以 `/` 开头、包含 `..` 或自行拼接查询串。查询参数使用 `params: { page: 1 }`。方法使用大写 `GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS`；`GET/HEAD` 不允许 `data`。可在第二个参数传入 `{ signal: controller.signal }` 取消请求。

返回值与宿主请求客户端的 JSON 返回值一致。本例 API 直接返回 JSON 对象；若自己的 API 使用 `{ code, data, msg }`，桥保留该结构，不额外替插件解包 `data`。当前桥只处理 JSON，每条消息最多 64 KiB，最多 8 个待处理请求，默认 15 秒超时；不支持 `FormData` 上传、文件/二进制下载、streaming、SSE 或 WebSocket 代理。

## 会话、权限与传输加密

`PluginFrame` 用宿主 Bearer 调用 `POST /plugin/runtime/bundle_demo/session`，取得最长 300 秒的短期会话，浏览器保存路径受限的 `HttpOnly; SameSite=Strict` Cookie，HTTPS 下添加 `Secure`。Redis 条目绑定用户、插件、版本、origin 与主会话摘要，不复制主 token；主登录剩余有效期更短时使用更短期限。多标签续期复用同一会话，不相互替换 CSRF。

UI、静态文件、API 每次访问均经过宿主门禁并回查主登录和当前权限。退出、主登录替换、插件停用或版本改变会使后续请求失效。具体 API 继续使用 `plugin_endpoint(..., permission='bundle_demo:view')` 或 `request.state.plugin_context.require_permission(...)`；仅隐藏菜单不能代替 API 权限。

子页面通过 `postMessage` 发送受校验的 JSON 请求，父页面使用已有加密 `request` 客户端，禁用自动添加主 Bearer，自动发送插件 Cookie 并添加 `X-Plugin-CSRF`。写请求同时校验精确同源 Origin。主 token、Cookie 和 CSRF 不进入 bridge 消息或插件 URL。Cookie 也不能替代其他宿主接口的 Bearer。

只读 `/apps/bundle_demo/ui/` 使用普通 HTTPS，HTML 当前 `Cache-Control: no-store`，其他静态文件 `no-cache`；资源仍需认证。`/apps/bundle_demo/api/...` 与会话签发接口继续遵守宿主传输加密，不能把 `/apps` 整段排除。真实加密测试已覆盖 JSON 信封、Cookie、CSRF、完整 API AAD 以及代理前缀。

同源插件属于可信代码。iframe 仅隔离布局和依赖；它不是阻止恶意插件读取同源数据的安全沙箱。现有主 token 在宿主前端可读，“桥不传 token”不等于不可信同源代码无法接触宿主凭证。

## 代理前缀与验证

默认 `VITE_APP_PLUGIN_BASE` 为空，浏览器从当前源访问 `/apps/` 和 `/plugin/runtime/`。宿主 Vite 已提供这两条保留原路径、Host 的开发代理，Docker Nginx 示例也已更新。

如果部署使用 `/prefix`，同时设置后端 `APP_ROOT_PATH=/prefix` 和宿主 `VITE_APP_PLUGIN_BASE=/prefix`，代理入口对应为 `/prefix/apps/`、`/prefix/plugin/runtime/`，转发时保留前缀与外部 Host。Cookie Path 和注入的运行基址会包含 `/prefix`；请求 AAD 剥离该前缀后仍保留 `/apps/bundle_demo/api/...`，不能缩短为 `/api/...`。可信代理和 ASGI 服务器须正确传递外部 HTTPS scheme，否则 Origin 或 Secure Cookie 行为会不一致。

从后端目录可执行定向验证：

```bash
python -m pytest tests/plugins/core/runtime/test_bundle.py tests/plugins/core/runtime/test_browser_session.py tests/plugins/core/runtime/test_bundle_transport.py tests/module_admin/service/test_login_plugin_routes.py -q
npm --prefix ../ruoyi-fastapi-frontend run test:plugin
```

测试覆盖静态边界、Cookie/CSRF/退出、真实 RSA/AES 协议和 `root_path`；数据库及登录查询使用替身。实际角色配置、TLS/Nginx、多 worker、既有 WebSocket 或长连接排空仍需部署验收，当前不提供这些连接的自动关闭协议。
