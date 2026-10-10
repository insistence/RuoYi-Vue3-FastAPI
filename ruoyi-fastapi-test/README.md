# RuoYi-FastAPI 项目测试套件

这里集中维护 RuoYi-FastAPI 的浏览器 E2E、跨工程时间契约和移动端行为测试。后端单元与契约测试位于 `ruoyi-fastapi-backend/tests`，前端各工程的测试位于自身 `tests` 目录。各前端框架共用后端，当前提供 Vue2、Vue3 实现。

## CI 分类与触发

统一入口 [ci.yml](../.github/workflows/ci.yml) 始终生成执行计划，再调用六个分类工作流：

| 分类 | 工作流 | 主要检查 |
| --- | --- | --- |
| Quality | [ci-quality.yml](../.github/workflows/ci-quality.yml) | Python/Web 格式、actionlint、选路与失败门禁测试、两框架 × 四份 Compose 配置 |
| Backend | [ci-backend.yml](../.github/workflows/ci-backend.yml) | Python 3.10–3.13 单元与契约、Windows CLI/路径、三种宿主时区 |
| Frontend | [ci-frontend.yml](../.github/workflows/ci-frontend.yml) | 四工程单元测试、三时区契约、Web prod/docker、移动端 H5/微信构建与 H5 登录 |
| Integration | [ci-integration.yml](../.github/workflows/ci-integration.yml) | 双数据库时间持久化、插件发布、Vue2/Vue3 HTTPS 代理与 SSE/WebSocket |
| E2E | [ci-e2e.yml](../.github/workflows/ci-e2e.yml) | 独立数据库和应用容器、Chromium 登录/权限/页面/时区及完整 CRUD |
| Native | [ci-native.yml](../.github/workflows/ci-native.yml) | Rust fmt/clippy、Windows/Linux × Python 3.10–3.13 的真实原生制品 |

PR 按 `.github/scripts/ci_plan.py` 的变更影响规则选择分类与前端工程。共享依赖和 CI 变更触发全部分类；仅文档变更运行 Quality。PR E2E 使用 Python 3.12，受影响的每个 Web 框架分别测试 MySQL 和 PostgreSQL，**每个组合都执行全部 `e2e` 用例，包括页面访问和业务操作**。`master` 推送、每天 UTC 18:21（北京时间次日 02:21）及手动 `full=true` 扩展为四个 Python 版本；`full` 只改变兼容矩阵，不再缩减功能测试范围。手动 `full=false` 运行所有分类的 PR 规模矩阵。

统一入口的 `Result` 是最终必需检查：被计划选中的分类必须成功，未选中分类才允许跳过。仓库管理员需要将分支保护的旧必需检查改为该检查。专用浏览器、原生和时区任务还检查 JUnit，防止零用例或缺依赖导致的跳过被当作通过。常规后端任务允许预期的平台跳过，但必须实际执行用例。

Python 测试保留 JUnit，后端任务记录慢项耗时；失败浏览器用例附带截图、trace、控制台与服务日志。下载对应 Actions artifact 即可定位问题，前端单元和构建输出可在 job 日志中查看。本地产物统一写入各工程 `target/ci`、`target/e2e` 或 `target/plugin-network-smoke/<framework>`。后端 `--durations` 用于持续观察慢项，不对执行时间设未经测量的目标。

## 按分类本地验证

以下命令在仓库根目录执行。后端按资源需求标记 `browser`、`native`、`integration`，不按目录名称排除测试；例如 `tests/plugins/integration` 中不需要真实服务的安全测试仍由 Backend 执行。

```bash
python -m pip install -r .github/requirements.txt
python -m pytest .github/tests -q
python .github/scripts/check_compose.py

cd ruoyi-fastapi-backend
python -m pip install -r requirements.txt -r requirements-test.txt
python ../.github/scripts/install_ai_test_dependencies.py
python -m pytest tests -m 'not browser and not native and not integration' --strict-markers --durations=20
```

四个前端工程统一提供 `npm run test:unit`、`npm run test:contract` 和 `npm test`。先按工程安装依赖：Web 使用 npm，Vue2 Mobile 使用 Yarn 1.22.22，Vue3 Mobile 使用 `package.json` 声明的 pnpm。Vue2 在 Node 18 及以上使用 `NODE_OPTIONS=--openssl-legacy-provider`。Vue2 Mobile 另有 `npm run test:bundle`，验证真实 webpack bundle 在缺少原生 Intl 时的行为。移动端行为测试使用真实请求、store、权限与时间模块，在网络和 uni API 边界使用隔离夹具；H5 浏览器测试加载实际构建，API 响应固定，不依赖业务数据库。

```bash
# 在对应前端工程执行
npm run test:unit
npm run test:contract
# Mobile 工程额外执行
npm run build:h5
npm run build:mp-weixin

# 返回仓库根目录，安装 Chromium 后验证实际 H5 构建
python -m pip install playwright==1.62.0
python -m playwright install chromium
python .github/scripts/mobile_smoke.py --framework vue2
python .github/scripts/mobile_smoke.py --framework vue3
```

## 功能特性

- 使用默认方式手动启动前后端服务或`Docker Compose`自动启动项目前后端服务
- 测试环境已禁用验证码功能
- 验证登录流程和认证机制
- 测试所有受保护的页面功能
- 验证未登录用户访问受保护页面时的重定向行为

## 依赖安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 使用方法

### 方式一：本机直接启动前后端（无需 Docker）

准备专用 MySQL 或 PostgreSQL 测试数据库和 Redis，分别用后端 `sql/ruoyi-fastapi.sql` 或 `sql/ruoyi-fastapi-pg.sql` 初始化数据。将后端 `.env.dev` 复制为本机 `.env.e2e`，替换其中的 `DB_SOURCES`、`REDIS_HOST`、`REDIS_PORT`、`REDIS_DATABASE`，指向这些专用服务，再用 `--env=e2e` 启动。浏览器测试会执行真实新增、修改、停用、删除和缓存操作；不要让测试配置连接开发或业务数据库。

#### 启动前端

```bash
# 以下各步骤均从仓库根目录进入目标工程
cd ruoyi-fastapi-frontend/vue3/web
# 使用 Vue2 时改为：cd ruoyi-fastapi-frontend/vue2/web
npm install
npm run dev -- --host 127.0.0.1 --port 8083
```

Vue2 可使用端口 `8082`。Node 18 及以上启动 Vue2 前，Bash 执行 `export NODE_OPTIONS=--openssl-legacy-provider`，PowerShell 执行 `$env:NODE_OPTIONS = '--openssl-legacy-provider'`；同时设置 `BROWSER=none`，避免开发服务自动打开浏览器。前端开发代理默认连接 `http://127.0.0.1:9099`；更改后端端口时也要调整对应工程的代理目标。

#### 启动后端

```bash
cd ruoyi-fastapi-backend
pip install -r requirements.txt
python app.py --env=e2e
```

启动前设置 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2` 或 `vue3`，与本轮待测工程一致。手动启动服务时，需要在专用测试数据库中将 `sys.account.captchaEnabled` 配置设为 `false` 并刷新配置缓存；Docker 测试配置会挂载 `disable_captcha.sql` 自动处理。不要对正在使用的业务环境运行这些会写入数据的 E2E。

#### 运行测试

```bash
cd ruoyi-fastapi-test
pip install -r requirements.txt
TEST_FRONTEND_URL=http://127.0.0.1:8083 TEST_BACKEND_URL=http://127.0.0.1:9099 TEST_SWAGGER_DISABLED=false \
  FRONTEND_FRAMEWORK=vue3 E2E_OUTPUT_DIR=target/e2e/vue3/browser \
  python -m pytest -m e2e -v --durations=20 --junitxml=target/e2e/vue3/junit.xml
python ../.github/scripts/check_test_report.py target/e2e/vue3/junit.xml
```

Windows PowerShell 等价示例（Vue2）：

```powershell
cd ruoyi-fastapi-test
$env:TEST_FRONTEND_URL = 'http://127.0.0.1:8082'
$env:TEST_BACKEND_URL = 'http://127.0.0.1:9099'
$env:FRONTEND_FRAMEWORK = 'vue2'
$env:TEST_SWAGGER_DISABLED = 'false'
$env:E2E_OUTPUT_DIR = 'target/e2e/vue2/browser'
python -m pytest -m e2e -v --durations=20 --junitxml=target/e2e/vue2/junit.xml
python ../.github/scripts/check_test_report.py target/e2e/vue2/junit.xml
```

`TEST_SWAGGER_DISABLED` 必须与后端 `APP_DISABLE_SWAGGER` 一致：开发配置默认 `false`，Docker 测试配置默认 `true`。完成 Vue2 后，切换后端插件框架配置、前端 URL、`FRONTEND_FRAMEWORK` 和输出目录，再独立执行 Vue3 全部用例。两个框架共用测试数据库或 Redis 时应顺序执行，避免缓存、强退和日志操作互相干扰。仅快速定位登录问题时可额外使用 `-m 'e2e and smoke'`，这不代表完整 E2E 验收。

### 方式二：使用Docker

#### 进入测试目录

```bash
cd ruoyi-fastapi-test
```

#### 启动 Docker 服务

测试目录的 `ruoyi-fastapi-test/docker.env` 默认设置 `FRONTEND_FRAMEWORK=vue3`，用于选择待测 Web 工程和 nginx 配置，当前可选值为 `vue2`、`vue3`。Compose 同时将该值作为 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK` 传入后端，使插件依赖检查和安装使用相同框架分类。测试 Vue2 Web 时，将其改为 `vue2`，或通过终端环境变量传入；各前端框架共用同一个后端镜像和测试数据库配置。进入测试目录后，执行下方命令，通过 `--env-file docker.env` 显式加载配置。

```bash
# MySQL版本
docker compose --env-file docker.env -f docker-compose.test.my.yml up -d --build
# PostgreSQL版本
docker compose --env-file docker.env -f docker-compose.test.pg.yml up -d --build
```

#### 运行测试

```bash
pip install -r requirements.txt
python -m pytest -m e2e -v --durations=20
```

### 方式三：复现 CI 独立容器环境

在测试目录执行下方命令生成专用项目。生成配置保留真实应用配置，移除固定容器名，使用随机 loopback 端口和专属网络/数据卷，避免与开发环境冲突。`--database` 可选 `mysql`、`postgresql`，`--framework` 可选 `vue2`、`vue3`。

```bash
python prepare_e2e_compose.py --database mysql --framework vue3 --python-version 3.12 --project ruoyi-ci-local --output target/e2e/compose.json
docker compose -f target/e2e/compose.json up -d --build --wait --wait-timeout 240
docker compose -f target/e2e/compose.json port ruoyi-frontend 80
docker compose -f target/e2e/compose.json port ruoyi-backend-my 9099
```

将上述两个地址加上 `http://`，分别写入终端环境变量 `TEST_FRONTEND_URL`、`TEST_BACKEND_URL`，并将 `FRONTEND_FRAMEWORK` 设置为生成配置时选择的框架；PostgreSQL 后端服务名为 `ruoyi-backend-pg`。Bash 使用 `export NAME=value`，PowerShell 使用 `$env:NAME = 'value'`。

```bash
python -m pytest -m e2e -v --durations=20 --junitxml=target/e2e/junit.xml
python ../.github/scripts/check_test_report.py target/e2e/junit.xml
docker compose -f target/e2e/compose.json down --volumes --remove-orphans
```

浏览器基础设施自身的测试通过 `python -m pytest -m harness -q` 执行，无需应用服务。所有用例复用会话级 Chromium，每个用例使用独立 context 和 API 客户端；断言失败后由 fixture 收集诊断并回收资源。可以通过 `TEST_BROWSER_CHANNEL=msedge` 或 `TEST_BROWSER_EXECUTABLE` 指定本机浏览器，默认使用 Playwright Chromium。

登录夹具和实际 UI 登录遇到 HTTP 429 时，按服务端 `Retry-After` 有界等待后重试，不修改后端限流配置。共用后端与 Redis 的完整用例应串行执行，避免争用同一限流桶；CI 使用独立资源的矩阵任务可以并行。

## 测试内容

### 登录测试

- 验证登录页面正常加载
- 验证登录流程（测试环境已禁用验证码）
- 测试认证后的页面访问

### 页面访问和功能测试

页面清单以两份初始化 SQL 的 `sys_menu` 中 29 个页面菜单及两版 Web 的实际 `router/views` 为依据。Vue2、Vue3 分别连接自身的真实构建或开发服务执行同一业务契约；不能仅更改矩阵标签而继续访问另一框架的页面。

| 页面范围（Vue2 / Vue3 均执行） | 实际路由 | 功能验收 |
| --- | --- | --- |
| 用户、角色、菜单、部门、岗位（5 页） | `/system/user`、`role`、`menu`、`dept`、`post` | 新增、查询、编辑、删除及相关授权功能 |
| 字典、参数、通知公告（3 页） | `/system/dict`、`config`、`notice` | 字典数据及业务记录增删改查 |
| 操作日志、登录日志（2 页） | `/system/log/operlog`、`/system/log/logininfor` | 查询、操作详情、单条删除和清空 |
| 文件（1 页） | `/system/file` | 公开/私有文件上传、查询、详情及哈希核对、下载字节核对、删除、恢复并再次下载、永久清理 |
| 插件（1 页） | `/system/plugin` | 搜索/空态/重置、清单详情各标签、运行指标刷新、依赖报告与安装计划、拓扑安装计划、审计查询与重置 |
| OAuth 应用、资源、范围（3 页） | `/system/oauth/client`、`resource`、`scope` | UI 新增、筛选、编辑、停用、启用；应用密钥一次性展示；API 核对持久化状态 |
| OAuth 会话、授权、签名密钥（3 页） | `/system/oauth/session`、`grant`、`key` | 会话筛选/重置/空态，访问禁止策略创建与解除，签名服务真实状态和轮换表单校验 |
| 在线用户、定时任务（2 页） | `/monitor/online`、`/monitor/job` | 登录后强退，任务配置与调度日志 |
| 数据、服务、缓存监控及缓存列表（4 页） | `/monitor/druid`、`server`、`cache`、`cacheList` | 真实服务/缓存数据、缓存操作；数据监控当前是应用自身的占位页面，只验证实际页面内容 |
| 传输加密、OAuth 审计（2 页） | `/monitor/transportCrypto`、`/monitor/oauthAudit` | 真实监控状态、刷新、审计查询与导出 |
| 表单构建、代码生成、系统接口（3 页） | `/tool/build`、`gen`、`swagger` | 表单组件及导出、生成配置与预览/下载、Swagger 配置对应的可用/关闭状态 |

此外覆盖首页、个人中心、字典数据、用户分配角色、角色分配用户、调度日志、代码生成配置等非菜单入口，以及登录守卫与三种浏览器时区。每个页面至少核对主体或特定业务组件；仅出现侧边栏标题不能证明目标页面加载成功。

账户与错误页另有独立交互用例：个人中心修改昵称、电话和邮箱后核对 API 持久化及刷新回显，再恢复原资料；锁屏验证空密码/错误密码拒绝、锁定期间的路由守卫以及正确密码返回锁前页面；401/404 返回首页后继续打开个人中心。认证中心登录、同意授权和改密入口使用真实功能状态接口，验证未启用或缺少交互上下文时进入错误说明页，并通过返回按钮回到原登录页，不依赖外部身份提供方或模拟响应。

OAuth 管理测试可以在默认 `OIDC_ENABLED=false` 配置下执行。签名密钥页核对真实服务状态与表单校验；会话页核对真实查询和空态，不声称已验收 OIDC 协议登录、会话撤销或签名密钥激活/退役。应用、资源、范围的删除接口按产品契约执行软停用，测试用唯一标识创建记录，并在结束时停用自己的记录、解除自己的访问禁止策略。

插件用例按真实运行能力核对开发预演或生产阻断：开发模式下验证依赖预演请求为 `dryRun=true`、策略为 `plan_only`、实际依赖安装按钮不可用；生产 `built/service` 模式下验证业务码 `601`、依赖异常或能力阻断的具体原因、警告提示及不可执行的操作。所有分支都验证没有实际安装请求，操作前后的安装版本、状态、启用设置不变；不会安装或卸载插件、执行依赖安装或清理插件审计日志。操作审计允许真实空数据，并验证筛选请求参数、返回列表与界面行数及重置行为。

### 认证测试

- 验证未登录用户访问受保护页面时被重定向到登录页
- 验证登录后可以访问受保护页面

## 通用时间契约

`time-contract` 按前端框架组织相同的时间工具回归测试，当前覆盖 Vue2、Vue3 的 Web、移动端和缺少原生 Intl 的移动端实现，验证 RFC 3339、日期合法性、epoch 单位、DST 缺失/重复时间和表单往返。固定时间样例用于验证边界行为，不依赖真实业务数据、数据库、浏览器、构建产物或 `.cache` 中预先生成的文件。

前端目录约定为 `ruoyi-fastapi-frontend/<framework>/{web,mobile}`，当前框架标识为 `vue2`、`vue3`。先在各工程中按依赖清单安装依赖，再从仓库根目录运行：

```bash
node ruoyi-fastapi-test/time-contract/run-host-timezones.mjs
# 也可只验证一个前端框架
node ruoyi-fastapi-test/time-contract/run-host-timezones.mjs vue2
node ruoyi-fastapi-test/time-contract/run-host-timezones.mjs vue3
```

脚本默认验证当前配置的全部前端框架（`vue2`、`vue3`），通过自身位置定位仓库，在 UTC、Asia/Shanghai 和 America/New_York 三个独立进程中执行；更换检出目录或从其他目录调用不影响路径解析。各工程中的测试入口负责导入自身时间工具，共享契约不写死本机绝对路径。CI 的插件前端测试和时间契约测试也按前端框架矩阵运行，当前包含 `vue2`、`vue3`。

## 配置说明

使用 `docker-compose.test.my.yml`或`docker-compose.test.pg.yml`启动服务，默认前端端口为 `80`，后端端口为 `9099`。测试环境已禁用验证码功能。

## 注意事项

1. 本机直接运行只需要数据库、Redis、Python、Node 和浏览器；只有容器方式需要 Docker 和 Docker Compose
2. 确保选用的前端端口与后端 `9099` 未被占用，测试 URL 与实际监听地址一致
3. 同一套测试数据库和 Redis 上顺序运行 Vue2、Vue3；每轮保留独立 JUnit 和浏览器诊断目录
4. 测试使用默认管理员账户：用户名 `admin`，密码 `admin123`
