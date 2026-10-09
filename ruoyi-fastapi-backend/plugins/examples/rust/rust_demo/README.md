# Rust 原生插件示例

本示例将业务实现编译成 PyO3 扩展，通过现有插件平台加载。默认创建 ASGI 子应用，也提供 Router 入口。Rust 可以调用已有 Python 工具，并通过宿主 SDK 调用用户资料服务。交付 ZIP 包含清单、原生扩展和包元数据，不包含 `.rs`、Cargo 文件或 Python 业务源码。

示例要求 Host API `^1.3.0`，新增 `POST /apps/rust_demo/api/echo/item-7?tag=first&tag=second`。使用宿主 Bearer 认证和 `rust_demo:view` 权限，发送 `{"message":"你好"}` JSON，即可收到 `pathParams`、保留同名多值的 `query`、`body` 和 `requestId`。Router 入口对应 `/rust_demo/api/echo/{item_id}`。Rust 从 `context.request.to_payload()` 读取宿主数据快照；SDK 负责体积限制、JSON 解析、权限及超时，不把认证头传入快照。

创建自有项目可使用 `ruoyi plugin create <id> --template rust-asgi` 或 `--template rust-bundle`，详见[脚手架与完整构建](../../../../docs/plugin_development.md#16-v2-项目脚手架与完整构建)。原生构建器也支持 bundle 组合：先独立构建清单指定的前端目录，再使用同一 `--source` / `--output` 命令组装；本示例本身仍为无前端的 API 示例。

## 构建

在仓库的 `ruoyi-fastapi-backend` 目录执行，先按 [CLI 环境准备](../../../../docs/cli_usage.md#22-安装依赖)激活已安装宿主依赖的 Python 环境。下文 `python` 使用当前环境，通用命令适用于 Windows PowerShell、macOS 和 Linux。

构建端需要 Rust 及目标平台编译工具：Windows 使用 Rust MSVC 工具链、Visual Studio Build Tools 的 C++ 工具和 Windows SDK；macOS 使用 Xcode Command Line Tools；Linux 使用 GCC 或 Clang 等编译工具。部署端使用构建好的匹配平台制品，无需安装 Rust。

```bash
python -m pip install 'maturin>=1.15,<2'
rustup toolchain install 1.99.0 --profile minimal --component rustfmt --component clippy
rustup default 1.99.0
python scripts/build_native_plugin.py --output target/native-package
```

若刚安装 Rust，重新打开终端使 Cargo 路径生效。构建命令使用当前 Python，使用已提交的 `Cargo.lock` 执行 release 构建；首次构建需取得锁定的 Rust 依赖。输出目录必须不存在，每次构建使用新目录。

输出布局：

```text
target/native-package/
  wheels/ruoyi_plugin_rust_demo-1.0.0-<python>-<abi>-<platform>.whl
  rust_demo/
    plugin.yaml
    native/
      ruoyi_plugin_rust_demo/__init__.py
      ruoyi_plugin_rust_demo/_native.<platform-extension>
      ruoyi_plugin_rust_demo-1.0.0.dist-info/...
  rust_demo-1.0.0.zip
```

构建器按当前解释器的 wheel tag 优先级选择发行包，校验名称、版本、Python 要求、已安装依赖及完整 RECORD SHA256，再展开至新目录。拒绝目录越界、链接、大小写冲突、未登记文件和超限解压。部署需选择与目标操作系统、架构和 Python 匹配的制品；Windows wheel 不能在 Linux 使用。本例声明 `abi3-py310`，仍需对实际运行平台分别验证。该构建脚本输出的目录 ZIP 不含发布者签名；签名及维护发布由下面的独立 CLI 完成。

## 本地集成验证

先指定已构建的交付目录。Windows PowerShell：

```powershell
$env:RUOYI_NATIVE_PLUGIN_DIR = (Resolve-Path 'target/native-package/rust_demo').Path
```

macOS / Linux（Bash、Zsh）：

```bash
export RUOYI_NATIVE_PLUGIN_DIR="$(pwd)/target/native-package/rust_demo"
```

然后运行测试和 Rust 检查（三种平台通用）：

```bash
python -m pytest tests/plugins/native tests/plugins/core/native tests/plugins/core/runtime/test_host_services.py tests/plugins/core/runtime/test_job_dispatcher.py -q
cargo fmt --manifest-path plugins/examples/rust/rust_demo/Cargo.toml --check
cargo clippy --manifest-path plugins/examples/rust/rust_demo/Cargo.toml --locked -- -D warnings
```

测试直接加载编译后的扩展，覆盖 ASGI、Router、原生 future、Python 协程桥、权限、异常、取消、lifespan 和真实 APScheduler 单次分发。数据库与登录使用替身；测试不会安装、启用插件或写入实际业务数据库。不设置环境变量时，真实原生测试明确跳过。

仓库的 `.github/workflows/native-plugin.yml` 配置 Windows/Linux、Python 3.10、3.11、3.12、3.13 构建测试矩阵。应以目标平台对应的实际构建与测试结果确认兼容性。

## 签名制品与维护发布

签名输入应是构建后的 `target/native-package/rust_demo`，其中已有 `native/` 扩展及发行包元数据；不要对包含 Cargo 工程的本示例源码目录或整个 `target/native-package` 打包。发布者先准备位于插件目录之外的 Ed25519 PKCS8 PEM 私钥；下列密钥路径仅为示例。

```bash
ruoyi plugin artifact build target/native-package/rust_demo target/rust_demo-1.0.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher --env=dev --output=json
ruoyi plugin artifact verify target/rust_demo-1.0.0.rpk --env=prod --output=json
ruoyi plugin artifact import target/rust_demo-1.0.0.rpk --env=prod --allow-prod --yes --output=json
```

宿主必须预先启用制品功能，在外部信任文件中配置该 keyId 的真实公钥并授权 `rust_demo`。包内公钥不能自行建立信任。导入不执行插件，也不安装或激活；它将完整内容保存到 `<store>/rust_demo/<version>/<digest>/payload/rust_demo`，后续使用重新检查当前信任与文件摘要。已有 `plugins/rust_demo` 目录会与制品部署冲突，迁移时应在维护窗口备份并移出。

取得导入返回的精确 digest 后，按[开发手册第 15 节](../../../../docs/plugin_development.md#15-v2-签名制品与维护发布)执行 plan、停机、prepare、读取 generation、select、重启与 status 检查。不能用相同版本号猜测准备完成的 digest；同版本但缺少对应准备证据时应提升版本。不要覆盖已加载二进制或直接修改不可变目录，运行期输出文件与缓存应写到制品目录之外。

代码回滚只选择上一制品并重启，要求旧代码兼容当前数据库，不执行数据库降级。相同内容重签不会改变 digest 或替换存储中的签名；旧签名撤销后应发布新版本/新内容，或在停机维护中显式处理旧对象及其索引引用。当前没有热卸载或自动清理制品的 CLI。

## 在开发环境安装

1. 将构建输出中的 `rust_demo` 目录复制至后端 `plugins/rust_demo`。部署的是构建产物目录，不是此源码目录。
2. 执行 `ruoyi plugin check rust_demo --env=dev`。
3. 执行 `ruoyi plugin install rust_demo --env=dev --yes` 和 `ruoyi plugin enable rust_demo --env=dev --yes`，然后重启后端。
4. 在现有角色权限管理中授予 `rust_demo:view` 和 `rust_demo:profile`，或使用具有通配权限的管理员。
5. 携带宿主 `Authorization: Bearer <token>` 调用下列接口。启用传输加密时仍须遵循宿主协议。

| 接口 | 行为 |
| --- | --- |
| `GET /apps/rust_demo/api/info` | Rust 调用已有 `TimezoneUtil.utc_now()` 并通过 Rust future 返回结果 |
| `GET /apps/rust_demo/api/profile` | Rust 调用 `host.service('users.current_profile.v1')`，返回当前登录用户的限定资料 DTO |

用户服务在调用边界核对插件身份、用户和 `rust_demo:profile` 权限，每次调用建立并关闭独立数据库会话，再复用现有 `UserService.user_profile_services()`。返回值不包含密码等内部字段。服务在宿主 Python 事件循环上执行，保留上下文与取消传播。需要业务事务时应另外设计明确的服务接口。

现有服务模式生命周期限制继续适用。生产变更应通过维护部署流程完成；不要覆盖已加载的二进制，升级后重启进程。

## Router 变体

在自己的插件清单中将 `backend.integration` 改为 `router`，删除 `backend.asgi`，将入口改为 `ruoyi_plugin_rust_demo._native:create_router_plugin`。重新构建或在未激活的交付目录调整清单，然后重启。接口前缀改为 `/rust_demo/api/`。同一插件 ID 只启用一种接入方式。

两种模式均使用 SDK 的 `plugin_endpoint(callback, permission=...)`，由宿主注入 `PluginRequestContext` 并执行权限检查。原生函数不需要让 FastAPI 直接反射参数签名。

## 定时任务

示例清单声明 `heartbeat`，默认 `enabled: false`，只记录一条日志并返回任务 ID。可通过现有任务管理的状态操作启用；此默认值不会赋予任何用户身份或业务权限。

v2 任务使用 `default` 异步执行器，`timeoutSeconds` 默认 30 秒。调度器保存稳定 Python 分发函数和 `[plugin_id, job_id, version]`，回调参数仍来自当前清单。执行前检查当前 worker 已就绪、版本一致、任务仍存在且插件已启用；随后传入 `PluginTaskContext(host, job_id)`，等待 Rust 或 Python awaitable。后台上下文没有请求用户，不能调用要求请求身份的用户资料接口。

进程关闭先停止分发，整批取消当前插件的任务并等待最多 5 秒，再关闭子应用资源。超时后继续其他清理，保留残留任务并阻止同名任务重新绑定，直到旧任务全部退出；迟到成功按取消记录。异步插件必须配合取消，等待上限不能强制终止阻塞的原生代码，也不能撤销已经执行的写操作。生命周期重试及关闭失败隔离见[开发手册](../../../../docs/plugin_development.md#67-asgi-子应用与生命周期)。不支持 v2 进程池任务，不提供原生模块热重载。多 worker 的调度选主继续沿用现有调度器，跨进程部署仍需单独验收。

## SDK 与使用说明

本例依赖 `Host API ^1.1.0`，`PluginDefinition.api_version` 仍为协议版本 `1`。宿主导出 `PluginHostContext`、`PluginRequestContext`、`PluginTaskContext`、`plugin_endpoint`、`plugin_lifespan` 和 `await_plugin_callback`。

通用清单、显式入口和 SDK 边界见[插件开发手册](../../../../docs/plugin_development.md#510-v2-清单与能力组合)。独立前端 bundle、PluginFrame 和浏览器专用会话桥的使用方式见 [Python bundle 示例](../../python/bundle_demo/README.md)；本 Rust 示例只提供 API，需要页面时可使用 `rust-bundle` 脚手架，并分别构建、验证原生后端和前端。签名制品与维护发布方式见上文，真实数据库与多 worker 的验收方法见[正式验收说明](../../../../docs/plugin_development.md#17-本地真实服务验收与-ci)。原生插件运行于宿主进程，应按可信扩展管理。

参考：[PyO3 调用 Python](https://pyo3.rs/main/python-from-rust/calling-existing-code)、[PyO3 异步互操作](https://pyo3.rs/main/ecosystem/async-await)、[Maturin](https://www.maturin.rs/)。
