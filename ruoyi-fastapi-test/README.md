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

PR 按 `.github/scripts/ci_plan.py` 的变更影响规则选择分类与前端工程。共享依赖和 CI 变更触发全部分类；仅文档变更运行 Quality。PR E2E 使用 Python 3.12，受影响的每个 Web 框架分别测试 MySQL 和 PostgreSQL。`master` 推送、每天 UTC 18:21（北京时间次日 02:21）及手动 `full=true` 扩展为四个 Python 版本和完整 CRUD；手动 `full=false` 运行所有分类的 PR 规模矩阵。

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

### 方式一：默认方法

#### 启动前端

```bash
# 以下各步骤均从仓库根目录进入目标工程
cd ruoyi-fastapi-frontend/vue3/web
# 使用 Vue2 时改为：cd ruoyi-fastapi-frontend/vue2/web
npm install
npm run dev
```

#### 启动后端

```bash
cd ruoyi-fastapi-backend
pip install -r requirements.txt
python app.py --env=dev
```

手动启动服务时，需要在专用测试数据库中将 `sys.account.captchaEnabled` 配置设为 `false` 并刷新配置缓存；Docker 测试配置会挂载 `disable_captcha.sql` 自动处理。不要对正在使用的业务环境运行这些会写入数据的 E2E。

#### 运行测试

```bash
cd ruoyi-fastapi-test
pip install -r requirements.txt
python -m pytest -m 'e2e and smoke' -v
# 全部应用 CRUD
python -m pytest -m e2e -v
```

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
python -m pytest -m 'e2e and smoke' -v
```

### 方式三：复现 CI 独立容器环境

在测试目录执行下方命令生成专用项目。生成配置保留真实应用配置，移除固定容器名，使用随机 loopback 端口和专属网络/数据卷，避免与开发环境冲突。`--database` 可选 `mysql`、`postgresql`，`--framework` 可选 `vue2`、`vue3`。

```bash
python prepare_e2e_compose.py --database mysql --framework vue3 --python-version 3.12 --project ruoyi-ci-local --output target/e2e/compose.json
docker compose -f target/e2e/compose.json up -d --build --wait --wait-timeout 240
docker compose -f target/e2e/compose.json port ruoyi-frontend 80
docker compose -f target/e2e/compose.json port ruoyi-backend-my 9099
```

将上述两个地址加上 `http://`，分别写入终端环境变量 `TEST_FRONTEND_URL`、`TEST_BACKEND_URL`；PostgreSQL 后端服务名为 `ruoyi-backend-pg`。Bash 使用 `export NAME=value`，PowerShell 使用 `$env:NAME = 'value'`。

```bash
python -m pytest -m 'e2e and smoke' -v --junitxml=target/e2e/junit.xml
python ../.github/scripts/check_test_report.py target/e2e/junit.xml
docker compose -f target/e2e/compose.json down --volumes --remove-orphans
```

浏览器基础设施自身的测试通过 `python -m pytest -m harness -q` 执行，无需应用服务。所有用例复用会话级 Chromium，每个用例使用独立 context 和 API 客户端；断言失败后由 fixture 收集诊断并回收资源。可以通过 `TEST_BROWSER_CHANNEL=msedge` 或 `TEST_BROWSER_EXECUTABLE` 指定本机浏览器，默认使用 Playwright Chromium。

## 测试内容

### 登录测试

- 验证登录页面正常加载
- 验证登录流程（测试环境已禁用验证码）
- 测试认证后的页面访问

### 页面访问和功能测试

- 仪表盘页面
- 用户管理页面
- 角色管理页面
- 菜单管理页面
- 部门管理页面
- 岗位管理页面
- 字典管理页面
- 参数配置页面
- 通知公告页面
- 日志管理页面（操作日志、登录日志）
- 在线用户页面
- 定时任务页面
- 服务监控页面
- 数据监控页面
- 缓存监控页面
- 缓存列表页面
- 代码生成页面
- 系统接口页面

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

1. 确保系统已安装 Docker 和 Docker Compose
2. 确保端口 `80` 和 `9099` 未被占用
3. 首次运行时 Docker 镜像构建可能需要几分钟时间
4. 测试使用默认管理员账户：用户名 `admin`，密码 `admin123`
