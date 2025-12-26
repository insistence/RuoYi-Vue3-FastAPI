# RuoYi-Vue3-FastAPI 项目测试套件

这是一个为 RuoYi-Vue3-FastAPI 项目创建的完整测试套件，使用 Playwright 进行端到端测试。测试环境已禁用验证码功能，以简化测试流程。

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
cd ruoyi-fastapi-frontend
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

```bash
# MySQL版本
docker compose -f docker-compose.test.my.yml up -d --build
# PostgreSQL版本
docker compose -f docker-compose.test.pg.yml up -d --build
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

## 配置说明

使用 `docker-compose.test.my.yml`或`docker-compose.test.pg.yml`启动服务，默认前端端口为 `80`，后端端口为 `9099`。测试环境已禁用验证码功能。

## 注意事项

1. 确保系统已安装 Docker 和 Docker Compose
2. 确保端口 `80` 和 `9099` 未被占用
3. 首次运行时 Docker 镜像构建可能需要几分钟时间
4. 测试使用默认管理员账户：用户名 `admin`，密码 `admin123`
