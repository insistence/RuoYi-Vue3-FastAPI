# 独立打包前端插件示例

本示例使用 **Python ASGI 后端 + 独立 Vite 前端 bundle**。页面通过宿主 `PluginFrame` 打开，取得宿主主题、语言、时区和路由状态，再通过通信桥调用查询、回显、上传检查、报表下载和 SSE 事件 API。欢迎语展示按需配置读取的用法；业务接口不保存消息或文件内容。

通用清单与后端入口见[插件开发手册](../../../../docs/plugin_development.md#510-v2-清单与能力组合)，浏览器集成协议见[bundle 页面与 SDK](../../../../docs/plugin_development.md#72-v2-独立-bundle-页面)。

前端交付 `web/dist`，不要求把插件页面加入宿主 Vue 源码或重新构建宿主。后端 `__init__.py` 仍是可读 Python 业务源码；需要保护后端源码时使用 [Rust 原生示例](../../rust/rust_demo/README.md)，并按 `native + asgi + bundle` 组合交付。编译前端也不保证浏览器端逻辑不可逆向。

## 构建前端

以下命令从仓库的 `ruoyi-fastapi-backend` 目录执行。Python 命令使用已安装宿主依赖的环境，准备步骤见 [CLI 环境准备](../../../../docs/cli_usage.md#22-安装依赖)。通用命令适用于 Windows PowerShell、macOS 和 Linux；Shell 语法不同的操作分别列出。构建端需已安装 Node.js/npm；部署端只使用构建产物，无需 Node.js。示例使用独立 `package.json`，不会把构建依赖写入宿主前端。

```bash
npm --prefix plugins/examples/python/bundle_demo/web install
npm --prefix plugins/examples/python/bundle_demo/web run build
```

首次安装会生成此示例自己的锁文件；独立维护插件时应保留锁文件，在 CI 中使用 `npm ci`。示例的 SDK 别名指向本仓库 `ruoyi-fastapi-frontend/src/utils/pluginBridge.js`。迁移到独立插件仓库时，将该模块及相邻的 `pluginBridge.d.ts` 一起复制为自己的版本化源码依赖，并调整 `vite.config.js` 中 `@ruoyi/plugin-bridge` 的别名。TypeScript 项目还应在自己的 `tsconfig.json` 中将同一别名映射到复制后的模块路径。

如果本仓库宿主前端依赖已安装，也可复用其中的 Vite 可执行文件构建**同一个插件前端项目**：

```bash
node ../ruoyi-fastapi-frontend/node_modules/vite/bin/vite.js build plugins/examples/python/bundle_demo/web --config plugins/examples/python/bundle_demo/web/vite.config.js
```

两种方式均输出 `plugins/examples/python/bundle_demo/web/dist`。配置使用 `base: './'`、关闭 sourcemap；宿主交付 HTML 时注入有效 `<base>` 和运行基址，因此资源和页面深层链接不需写死域名或代理前缀。直接用 `file://` 打开 dist 不会建立宿主身份桥；真实账号交互应从管理平台的插件菜单进入。

## 本地模拟宿主

安装示例依赖后，从后端目录运行：

```bash
npm --prefix plugins/examples/python/bundle_demo/web run dev
```

开发服务只监听本机，自动打开 `/dev.html`。模拟宿主使用真实通信桥，提供主题切换、0–5000 毫秒延迟、故障注入、页面重载和退出；上传检查、下载与逐条事件在浏览器内存中完成，不调用实际后端。事件间隔最短 100 毫秒，可停止后按游标继续。刷新整个页面可恢复模拟退出后的会话。

`web/dev/mockRequest.js` 是可扩展的纯请求适配器，可按业务补充本地响应；真实插件界面位于 `web/src/main.js`。Vite 仅在开发服务为插件入口注入模拟标识，生产构建只包含插件入口和其依赖，不包含开发宿主。模拟环境不能验证真实登录、权限、CSRF、反向代理或传输加密，这些仍需在宿主内验证。

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
Copy-Item -LiteralPath (Join-Path $bundleSource 'files.py') -Destination $bundlePackage
Copy-Item -LiteralPath (Join-Path $bundleSource 'events.py') -Destination $bundlePackage
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
    cp "$bundleSource/plugin.yaml" "$bundleSource/__init__.py" "$bundleSource/files.py" "$bundleSource/events.py" "$bundlePackage/"
    cp -R "$bundleDist" "$bundlePackage/web/dist"
    python -m zipfile -c "$bundleRelease/bundle_demo-1.0.0.zip" "$bundlePackage"
)
```

ZIP 内布局：

```text
bundle_demo/
  plugin.yaml
  __init__.py
  files.py
  events.py
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

制品目录保持不可变，不手工替换页面资源、入口或 Python 模块。代码回滚要求旧代码兼容现有数据结构，不会回退数据库。相同内容重签不改变 digest，可通过 `artifact rotate-signature` 在维护模式下轮换签名；`artifact inspect/prune/reconcile` 提供预览、受保护清理和中断恢复。上述写操作仍需停止全部 worker，不自动热卸载或停止进程。完整流程和故障处理见开发手册。

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

`plugin.yaml` 使用 Host API `^1.4.0`，供欢迎语接口调用 `host.read_config()`。基础 bundle 协议仍兼容 `^1.2.0`；文件与 SSE 能力由前端握手协商，首次使用时需要更新并构建支持这些能力的宿主前端。菜单组件为 `PluginFrame`，后端根据 `sys_plugin_menu` 的真实关联返回 `meta.pluginId`；不从路径或 `query.pluginId` 推测插件。只有已启用、已激活且用户有权限的 bundle 可以签发浏览器会话。

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

返回值与宿主请求客户端的 JSON 返回值一致。本例 API 直接返回 JSON 对象；若自己的 API 使用 `{ code, data, msg }`，桥保留该结构，不额外替插件解包 `data`。JSON 请求和文件元数据每条最多 64 KiB，所有请求合计最多 8 个待处理任务，JSON 默认 15 秒、文件默认 120 秒超时。SSE 通过 `stream` 单独接收，不支持任意字节流或 WebSocket 代理。

```javascript
const controller = new AbortController()
const options = {
  signal: controller.signal,
  onProgress: ({ loaded, total }) => console.log(loaded, total),
}
const file = document.getElementById('file').files[0]
const inspection = await client.upload({ path: 'files/inspect', file }, options)
const report = await client.download({ path: 'files/report' }, options)
```

单文件最多 10 MiB；`upload` 接受 File/Blob，宿主重建 multipart，默认字段名 `file`、方法 POST，可使用 `fieldName/filename/fields/params`，其中 `fields` 的值只能是字符串。后端 `files.py` 检查权限及实际字节数，返回 SHA-256 摘要，不保存内容。`download` 返回 Blob，由页面决定保存名称并释放对象 URL。进度的 `total` 可能为 `null`；上传字节数可能包含 multipart 开销，进度到达 100% 后仍应等待 Promise 完成。页面已提供取消按钮、错误反馈和重试入口。旧宿主未公布 `capabilities.files.version=1` 时，SDK 会明确拒绝文件传输。

## SSE 实时事件

页面“接收实时事件”通过 `client.stream({ path: 'events', params: { count: 10 }, lastEventId }, { signal, onEvent })` 逐条显示最近 5 条事件；“停止接收”取消连接，“继续接收”传回最后成功处理的 id。正常完成后重新开始，页面重载会清空游标。`events.py` 的 GET `/api/events` 要求 `bundle_demo:view` 权限，默认每 0.5 秒发送一条 `tick`，最多 20 条。游标是事件编号；补发仅演示后续编号，重新生成服务端时间，不代表持久化历史重放。

`onEvent` 接收 `{ event, data, id }`，其中 `data` 为字符串，可返回 Promise。宿主等待处理完成才发送下一条，回调失败或超过 15 秒会关闭连接。每页最多 2 条流、每条最多 5 分钟，单事件最多 64 KiB、累计最多 10 MiB；超限或异常会拒绝返回的 Promise，正常 EOF 则完成。SDK 不自动重连；按业务实现退避、去重及恢复，并为重试创建新的 AbortController。恢复用 `lastEventId` 只接受最多 1024 个可打印 ASCII 字符。旧宿主未公布 `capabilities.streams.version=1` 时会明确拒绝，需要更新宿主前端。完整调用示例见[浏览器 SDK](../../../../docs/plugin_development.md#73-bundle-浏览器-sdk)。

## 配置读取与状态

安装后在管理页修改“页面欢迎语”，保存后回到本插件点击“刷新状态”。查询接口调用 `await context.host.read_config()`，从新的数据库会话取得当前插件的配置快照，并仅向页面返回公开的欢迎语字段；配置中的敏感值不能直接交给浏览器。

`host.config` 和 `host.config_revision` 始终保留启动快照，按需读取不会修改它们。管理页展示保存版本、各进程启动版本和最近按需读取版本；“待重启”针对启动快照，不否定本示例主动读取的欢迎语已经更新。连接池等启动资源需要插件自行应用或按部署流程重启。状态只有已观测进程的证据，不代表全部 worker 已经一致，详见[配置生效状态](../../../../docs/plugin_development.md#81-启动快照按需读取与生效状态)。

## 会话、权限与传输加密

`PluginFrame` 用宿主 Bearer 调用 `POST /plugin/runtime/bundle_demo/session`，取得最长 300 秒的短期会话，浏览器保存路径受限的 `HttpOnly; SameSite=Strict` Cookie，HTTPS 下添加 `Secure`。Redis 条目绑定用户、插件、版本、origin 与主会话摘要，不复制主 token；主登录剩余有效期更短时使用更短期限。多标签续期复用同一会话，不相互替换 CSRF。

UI、静态文件、API 每次访问均经过宿主门禁并回查主登录和当前权限。退出、主登录替换、插件停用或版本改变会使后续请求失效。具体 API 继续使用 `plugin_endpoint(..., permission='bundle_demo:view')` 或 `request.state.plugin_context.require_permission(...)`；仅隐藏菜单不能代替 API 权限。

子页面通过 `postMessage` 发送受校验的 JSON、文件或事件消息；父页面的 JSON/文件使用已有 `request` 客户端，SSE 使用增量 fetch 适配器。两者禁用主 Bearer，自动发送插件 Cookie 并添加 `X-Plugin-CSRF`。写请求同时校验精确同源 Origin。主 token、Cookie 和 CSRF 不进入 bridge 消息或插件 URL。Cookie 也不能替代其他宿主接口的 Bearer。

只读 `/apps/bundle_demo/ui/` 使用普通 HTTPS，HTML 当前 `Cache-Control: no-store`，其他静态文件 `no-cache`；资源仍需认证。`/apps/bundle_demo/api/...` 与会话签发接口继续遵守宿主传输加密，不能把 `/apps` 整段排除。真实加密测试已覆盖 JSON 信封、Cookie、CSRF、完整 API AAD 以及代理前缀。

文件上传下载不使用 JSON 加密信封，依赖 HTTPS 传输。若启用 `required` 模式，须在已有 `TRANSPORT_CRYPTO_EXCLUDE_PATHS` 列表中追加 `/apps/bundle_demo/api/files/inspect,/apps/bundle_demo/api/files/report` 两个精确端点；后端标准化路径不含代理前缀。保留现有例外，不排除整个插件 API；未经配置的文件请求仍会被拒绝。插件身份、权限、Origin 和 CSRF 校验在例外端点上仍然执行。反向代理也应设置符合业务要求的文件大小限制。

同源插件属于可信代码。iframe 仅隔离布局和依赖；它不是阻止恶意插件读取同源数据的安全沙箱。现有主 token 在宿主前端可读，“桥不传 token”不等于不可信同源代码无法接触宿主凭证。

SSE 同样依赖 HTTPS，不支持 JSON 加密信封；当前策略会加密事件端点时，需在既有例外列表中追加精确路径 `/apps/bundle_demo/api/events`（不含代理前缀），保留其他 API 的加密。宿主会先检查策略，拒绝未配置的流请求，不会自动降级。反向代理须关闭该接口的响应缓冲并配置超时，示例同时返回 `X-Accel-Buffering: no`。宿主退出、重载和会话失效会取消当前页面的流，但服务端不会对已经建立的连接持续重新鉴权；业务长连接需自行响应权限或插件状态变化。

## 代理前缀与验证

默认 `VITE_APP_PLUGIN_BASE` 为空，浏览器从当前源访问 `/apps/` 和 `/plugin/runtime/`。宿主 Vite 已提供这两条保留原路径、Host 的开发代理，Docker Nginx 示例也已更新。

如果部署使用 `/prefix`，同时设置后端 `APP_ROOT_PATH=/prefix` 和宿主 `VITE_APP_PLUGIN_BASE=/prefix`，代理入口对应为 `/prefix/apps/`、`/prefix/plugin/runtime/`，转发时保留前缀与外部 Host。Cookie Path 和注入的运行基址会包含 `/prefix`；请求 AAD 剥离该前缀后仍保留 `/apps/bundle_demo/api/...`，不能缩短为 `/api/...`。可信代理和 ASGI 服务器须正确传递外部 HTTPS scheme，否则 Origin 或 Secure Cookie 行为会不一致。

从后端目录可执行定向验证：

```bash
python -m pytest tests/plugins/core/runtime/test_bundle.py tests/plugins/core/runtime/test_browser_session.py tests/plugins/core/runtime/test_bundle_transport.py tests/plugins/core/runtime/test_bundle_files.py tests/plugins/core/runtime/test_bundle_events.py tests/plugins/core/runtime/test_configuration.py tests/module_admin/service/test_login_plugin_routes.py -q
npm --prefix ../ruoyi-fastapi-frontend run test:plugin
```

测试覆盖静态边界、Cookie/CSRF/退出、真实 RSA/AES 协议、文件大小和 `root_path`；浏览器会话测试替换真实账号查询，配置读取测试使用隔离 SQLite 验证保存、解密及重启版本。实际角色配置、TLS/Nginx、多 worker、既有 WebSocket 或长连接排空仍需部署验收，当前不提供这些连接的自动关闭协议。
