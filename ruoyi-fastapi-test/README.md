# RuoYi-FastAPI 项目测试套件

这是一个为 RuoYi-FastAPI 项目创建的完整测试套件，使用 Playwright 进行端到端测试。各前端框架的 Web 工程共用后端，当前提供 Vue2、Vue3 实现，默认测试 Vue3 Web。测试环境已禁用验证码功能，以简化测试流程。

## 功能特性

- 使用默认方式手动启动前后端服务或`Docker Compose`自动启动项目前后端服务
- 测试环境已禁用验证码功能
- 验证登录流程和认证机制
- 测试所有受保护的页面功能
- 验证未登录用户访问受保护页面时的重定向行为

## 依赖安装

```bash
pip install -r requirements.txt
playwright install
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

#### 运行测试

```bash
cd ruoyi-fastapi-test
pip install -r requirements.txt
python -m pytest -v
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
python -m pytest -v
```

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
