# RuoYi Backend CLI 使用文档

## 1. 文档说明

本文档用于说明 `ruoyi-fastapi-backend` 当前已经落地的 CLI 用法。

统一命令入口为：

```bash
ruoyi <group> <command> [options]
```

当前已实现的命令组包括：

- `app`
- `db`
- `ops`
- `cache`
- `job`
- `config`
- `crypto`
- `gen`
- `dev`
- `completion`
- `wizard`
- `tui`

## 2. 快速开始

### 2.1 执行目录

`ruoyi` 命令必须在后端项目根目录执行，也就是 `ruoyi-fastapi-backend` 目录。

```bash
cd ruoyi-fastapi-backend
ruoyi --help
```

### 2.2 安装依赖

MySQL 版本：

```bash
cd ruoyi-fastapi-backend
pip3 install -r requirements.txt
```

PostgreSQL 版本：

```bash
cd ruoyi-fastapi-backend
pip3 install -r requirements-pg.txt
```

说明：

- `requirements*.txt` 已包含当前项目自身安装项 `.`，因此不需要额外执行 `pip install -e .`
- 安装完成后，`ruoyi` 会随当前 Python 环境一起可用

如果本地使用 Conda，推荐先进入项目环境再执行命令：

```bash
conda activate ruoyi-fastapi
cd ruoyi-fastapi-backend
ruoyi --help
```

`textual` 已包含在现有依赖文件中，因此安装 `requirements.txt` 或 `requirements-pg.txt` 后即可直接使用 TUI。

### 2.3 第一个命令

开发环境启动应用：

```bash
ruoyi app run --env=dev
```

这个命令的目标是等价替代：

```bash
python app.py --env=dev
```

## 3. 使用规则

### 3.1 根参数位置

根参数必须写在命令组前面。

正确示例：

```bash
ruoyi --color=never --icon=none ops health --env=dev
```

推荐不要写成把根参数放到子命令后面的形式。

### 3.2 环境参数

CLI 不单独维护配置系统，仍然复用项目原有的 `config/env.py` 解析逻辑。

常用环境映射如下：

- `--env=dev` -> `.env.dev`
- `--env=prod` -> `.env.prod`
- `--env=dockermy` -> `.env.dockermy`
- `--env=dockerpg` -> `.env.dockerpg`

### 3.3 帮助命令

可以通过以下方式逐层查看帮助：

```bash
ruoyi --help
ruoyi app --help
ruoyi app run --help
ruoyi db --help
ruoyi cache clear --help
```

### 3.4 输出模式

除 `app run` 这类进程接管型命令外，大多数命令支持：

- `--output=text`
- `--output=json`

推荐约定：

- 人工排查优先使用 `text`
- 脚本集成优先使用 `json`
- `text` 输出中的字段名统一使用 `snake_case`
- `json` 输出中的字段名保持稳定结构化契约，不为显示效果重命名
- `json` 输出不会混入颜色码、emoji 或装饰文本
- `json` 输出不会混入 SQLAlchemy SQL 日志、普通业务日志或其他非 JSON 文本
- `app run` 会直接接管应用前台进程，因此不提供 `--output`

示例：

```bash
ruoyi ops health --env=dev --output=text
ruoyi ops health --env=dev --output=json
```

### 3.5 视觉选项

根命令支持：

- `--color=auto|always|never`
- `--icon=emoji|ascii|none`

当前默认值为：

- `--color=always`
- `--icon=emoji`

说明：

- 这两个参数只影响 `text` 输出
- `json` 输出始终保持结构化结果，不受颜色和图标影响

示例：

```bash
ruoyi --color=always ops server-info --env=dev
ruoyi --color=never ops server-info --env=dev
ruoyi --icon=none ops server-info --env=dev
```

### 3.6 危险命令

会产生真实副作用的命令会纳入危险命令保护。

危险命令分为两类：

- `high`：必须支持 `--dry-run` 或等价预览能力
- `normal`：默认要求确认，但不强制要求 `--dry-run`

保护规则如下：

- 非 `prod` 环境下默认会要求确认
- 非交互终端中如果未传 `--yes`，命令会直接拒绝执行
- `prod` 环境下默认禁止执行，必须显式传入 `--allow-prod --yes`
- 只有 `high` 风险命令或已实现预演能力的命令才会出现 `--dry-run`

示例：

```bash
ruoyi cache clear --env=dev --all --yes
ruoyi db upgrade --env=prod --revision=head --allow-prod --yes
ruoyi gen export sys_user --env=dev --mode=local --dry-run
```

## 4. 常用工作流

### 4.1 本地开发启动

```bash
cd ruoyi-fastapi-backend
ruoyi app doctor --env=dev
ruoyi app run --env=dev
```

### 4.2 发布前检查

```bash
ruoyi ops health --env=prod --output=json
ruoyi ops server-info --env=prod
ruoyi db current --env=prod --output=json
```

### 4.3 数据库迁移

```bash
ruoyi db check --env=dev
ruoyi db revision --env=dev --message="add user index" --yes
ruoyi db upgrade --env=dev --revision=head --yes
```

### 4.4 缓存与调度排查

```bash
ruoyi cache stats --env=dev
ruoyi cache keys sys_config --env=dev --output=json
ruoyi job list --env=dev --output=json
ruoyi job sync --env=dev --yes
```

### 4.5 开发态检查

```bash
ruoyi dev lint cli --check-only
ruoyi dev test tests --keyword sanitize --maxfail=1 -q
```

### 4.6 Shell Completion 初始化

```bash
ruoyi completion doctor --output=json
ruoyi completion show bash
ruoyi completion install --activate
ruoyi completion install --shell=bash --activate
```

### 4.7 交互式向导与 TUI

```bash
ruoyi wizard app-run
ruoyi wizard db-upgrade
ruoyi wizard cache-clear
ruoyi wizard gen-export
ruoyi wizard gen-import
ruoyi wizard prod-check
ruoyi tui --env=dev
```

## 5. 命令速查

### 5.1 `app`

用于启动当前 FastAPI 应用、启动前检查、配置快照和路由巡检。

```bash
ruoyi app run --env=dev
ruoyi app doctor --env=dev --output=json
ruoyi app env --env=dev
ruoyi app config --env=dev --output=json
ruoyi app routes --env=dev
ruoyi app routes --env=dev --method=GET --path-prefix=/system
ruoyi app routes --env=dev --group-by=tag
ruoyi app routes --env=dev --include-hidden --output=json
```

### 5.2 `db`

用于数据库连接检查和 Alembic 迁移封装。

```bash
ruoyi db check --env=dev
ruoyi db current --env=dev --output=json
ruoyi db heads --env=dev --output=json
ruoyi db history --env=dev --limit=10
ruoyi db upgrade --env=dev
ruoyi db upgrade --env=dev --revision=head --dry-run
ruoyi db init --env=dev
ruoyi db downgrade --env=dev --revision=-1
ruoyi db downgrade --env=dev --revision=-1 --dry-run
ruoyi db revision --env=dev --message="add user index" --yes
ruoyi db revision --env=dev --message="sync table structure" --autogenerate --yes
```

### 5.3 `ops`

用于基础运维检查。

```bash
ruoyi ops deps --env=dev
ruoyi ops ping-db --env=dev
ruoyi ops ping-redis --env=dev
ruoyi ops health --env=dev
ruoyi ops health --env=dev --output=json
ruoyi ops server-info --env=dev
ruoyi ops server-info --env=dev --output=json
```

说明：

- `server-info --output=text` 适合人工巡检
- `server-info --output=json` 更适合脚本消费

### 5.4 `cache`

用于缓存统计、查询、清理和预热。

```bash
ruoyi cache stats --env=dev
ruoyi cache stats --env=dev --output=json
ruoyi cache keys login_tokens --env=dev --output=json
ruoyi cache get sys_config site.name --env=dev --output=json
ruoyi cache ttl sys_config site.name --env=dev --output=json
ruoyi cache clear --env=dev --cache-name=sys_config --yes
ruoyi cache clear --env=dev --cache-key=site.name --yes
ruoyi cache clear --env=dev --all --yes
ruoyi cache warmup --env=dev --yes
```

### 5.5 `job`

用于定时任务查询、执行和同步。

```bash
ruoyi job list --env=dev --output=json
ruoyi job list --env=dev --job-name=同步任务 --status=0 --paged
ruoyi job detail 1 --env=dev --output=json
ruoyi job logs --env=dev --output=json
ruoyi job logs --env=dev --job-name=同步任务 --status=1 --paged
ruoyi job run-once 1 --env=dev --yes
ruoyi job pause 1 --env=dev --yes
ruoyi job resume 1 --env=dev --yes
ruoyi job sync --env=dev --yes
ruoyi job run-once 1 --env=prod --allow-prod --yes
```

### 5.6 `config`

用于系统参数配置读取、写入和缓存同步。

```bash
ruoyi config list --env=dev --output=json
ruoyi config list --env=dev --paged
ruoyi config get <config-key> --env=dev --output=json
ruoyi config get <config-key> --env=dev --source=both --output=json
ruoyi config get <config-key> --env=dev --source=db --output=json
ruoyi config get <config-key> --env=dev --source=cache
ruoyi config doctor --env=dev --output=json
ruoyi config set sys.user.initPassword --env=dev --value=123456 --name="初始密码" --yes
ruoyi config set sys.user.initPassword --env=dev --value=123456 --remark="CLI update" --yes
ruoyi config sync-cache --env=dev --yes
```

说明：

- `config get --source=both` 会同时读取数据库和 Redis，并在 JSON 中返回 `database`、`cache` 与 `inSync`
- `config get --source=db` 只读取参数配置表，适合确认数据库中的真实存量值
- `config get --source=cache` 只读取 Redis 缓存，适合确认当前运行时命中的值
- 如果某个键只在缓存里存在、不在数据库里存在，`--source=db` 会返回“参数配置不存在”，这代表数据库侧没有对应记录，不表示缓存读取异常

### 5.7 `crypto`

用于传输加密配置校验、公钥导出和密钥辅助操作。

```bash
ruoyi crypto validate --env=dev --output=json
ruoyi crypto keygen --env=dev --kid=default --key-size=2048
ruoyi crypto keygen --env=dev --output=json --kid=default --key-size=2048
ruoyi crypto export-public --env=dev
ruoyi crypto export-public --env=dev --output=json
ruoyi crypto rotate --env=dev --output=json --next-kid=v2 --key-size=2048 --yes
```

说明：

- `crypto keygen` 会输出新生成的公钥、私钥和建议写入的 `envPatch`
- `crypto rotate` 当前只生成轮换辅助结果，不会直接改写 `.env.*` 文件
- 涉及私钥的输出只建议在安全终端中使用

### 5.8 `gen`

用于代码生成业务表查询、导入、建表、预览和导出。

```bash
ruoyi gen list --env=dev --output=json
ruoyi gen db-list --env=dev --output=json
ruoyi gen detail 1 --env=dev --output=json
ruoyi gen import-table sys_user sys_role --env=dev --yes
ruoyi gen import-table sys_user sys_role --env=dev --dry-run
ruoyi gen create-table --env=dev --sql="create table demo_test (id bigint primary key)" --yes
ruoyi gen create-table --env=dev --sql-file=./sql/demo.sql --dry-run
ruoyi gen preview 1 --env=dev
ruoyi gen preview 1 --env=dev --output=json
ruoyi gen export sys_user --env=dev --yes
ruoyi gen export sys_user sys_role --env=dev --mode=zip --output-file=./build/gen.zip --yes
ruoyi gen export sys_user --env=dev --mode=local --dry-run
ruoyi gen sync-db sys_user --env=dev --yes
```

说明：

- `import-table` 与 `create-table` 支持 `--dry-run`
- `create-table` 必须且只能传入 `--sql` 或 `--sql-file` 其中一种
- `gen preview --output=text` 会按模板分块展示预览代码内容
- `export --mode=local` 会复用现有生成逻辑，并遵守 `GenConfig.allow_overwrite`

### 5.9 `dev`

用于开发态代码检查与测试执行。

```bash
ruoyi dev lint
ruoyi dev lint cli tests --check-only
ruoyi dev lint cli --fix
ruoyi dev lint cli --output=json
ruoyi dev test
ruoyi dev test tests/test_log_sanitize_util.py
ruoyi dev test tests --keyword sanitize --maxfail=1 -q
ruoyi dev test tests --output=json
```

说明：

- `dev lint` 默认顺序是先执行 `ruff format`，再执行 `ruff check`
- `--check-only` 会改成只检查，不写回
- `--fix` 会执行 `ruff check --fix`
- `dev test` 通过当前环境的 `python -m pytest` 执行测试

### 5.10 `completion`

用于生成、安装和诊断 shell completion。

```bash
ruoyi completion doctor --output=json
ruoyi completion show bash
ruoyi completion show zsh
ruoyi completion show fish
ruoyi completion show powershell
ruoyi completion install --activate
ruoyi completion install --shell=bash
ruoyi completion install --shell=zsh --activate
ruoyi completion install --shell=fish
ruoyi completion install --shell=powershell --activate
```

说明：

- 当前版本已支持 `bash`、`zsh`、`fish`、`powershell`
- `install` 在未传 `--shell` 时会优先自动识别当前 shell
- `install` 默认写入 shell 对应的默认脚本位置
- Bash 和 Zsh 如需自动加载，建议配合 `--activate`
- PowerShell 如需自动加载，建议配合 `--activate`
- Bash 脚本已对旧版本 Bash 做兼容处理，若之前已安装过脚本，请重新执行一次 `ruoyi completion install --activate`
- `completion doctor` 会给出推荐安装命令和 source 建议
- 当前已补充的上下文补全包括 `--env`、`cache_name`、`cache_key`、`config_key`、`db --revision`、`gen` 业务表名、`gen` 数据库表名、`gen --sql-file`、`gen --output-file`、`job_name`、`job_id`

### 5.11 `wizard`

用于通过交互方式组装危险命令或复杂命令，并在真正执行前输出预览。

```bash
ruoyi wizard app-run
ruoyi wizard db-upgrade --default-env=dev --default-revision=head
ruoyi wizard cache-clear --default-env=dev --default-mode=cache-name
ruoyi wizard gen-export --default-env=dev --default-mode=zip
ruoyi wizard gen-import --default-env=dev --default-table-names=sys_notice
ruoyi wizard prod-check --default-env=prod
```

说明：

- 所有向导都会先采集输入，再输出预览摘要与最终将执行的 CLI 命令
- `db-upgrade`、`cache-clear`、`gen-export`、`gen-import` 默认都支持先走 `dry-run`
- 向导本质上仍然是对底层 CLI 的封装，最终返回值、退出码和危险命令保护规则与底层命令保持一致

### 5.12 `tui`

用于进入只读巡检工作台，以页面方式浏览应用、运维、数据库、缓存、任务、代码生成、参数配置和加密状态。

```bash
ruoyi tui --env=dev
ruoyi tui --env=prod
```

说明：

- 当前 TUI 是只读巡检工作台，页面内的写操作入口会通过确认弹窗或向导二次确认
- 页面切换快捷键为 `D/A/O/B/C/T/G/P/E`，分别对应总览、应用、运维、数据库、缓存、任务、代码生成、参数配置、加密
- 通用快捷键包括 `R` 刷新、`Q` 退出、`S` 聚焦侧栏、`←/→` 切换焦点或区域、`J/K` 滚动、`PgUp/PgDn` 翻页、`Home/End` 首尾跳转
- 若当前 Python 环境缺少 TUI 依赖，`ruoyi tui` 会返回失败结果并提示重新执行 `pip install -r requirements.txt` 或 `pip install -r requirements-pg.txt`

## 6. 危险命令清单

当前已接入保护的命令包括：

- `cache clear`
- `cache warmup`
- `db upgrade`
- `db init`
- `db downgrade`
- `db revision`
- `config set`
- `config sync-cache`
- `crypto rotate`
- `job run-once`
- `job pause`
- `job resume`
- `job sync`
- `gen import-table`
- `gen create-table`
- `gen export`
- `gen sync-db`

说明：

- 在 `prod` 环境下，这些命令默认拒绝执行
- 在非 `prod` 环境下，这些命令默认也会进入交互确认
- 在非交互终端中，如果未传入 `--yes`，命令会直接拒绝执行
- 如果命令支持 `--dry-run`，优先先跑一次预演

## 7. 输出与退出码

### 7.1 输出格式

CLI 支持两种输出格式：

- `text`
- `json`

字段命名约定：

- `text` 输出优先面向人工阅读，字段名统一使用 `snake_case`
- `json` 输出优先面向脚本消费，字段名保持命令契约定义，不因视觉优化变化

示例：

```bash
ruoyi ops health --env=dev --output=json
```

标准样例：

文本输出样例：

命令：

```bash
ruoyi --color=never --icon=none app config --env=dev
```

输出：

```text
OK SUCCESS
env: dev
application:
  name: RuoYi-FastAPI
  host: 0.0.0.0:9099
  root_path: /dev-api
  reload: true
  workers: 1
  disable_swagger: false
  disable_redoc: false
database:
  type: mysql
  host: 127.0.0.1:3306
  name: ruoyi-fastapi
redis:
  host: 127.0.0.1:6379
logging:
  level: INFO
transport_crypto:
  enabled: false
  mode: off
```

JSON 输出样例：

命令：

```bash
ruoyi app config --env=dev --output=json
```

输出：

```json
{
  "ok": true,
  "env": "dev",
  "config": {
    "env": "dev",
    "name": "RuoYi-FastAPI",
    "host": "0.0.0.0",
    "port": 9099,
    "rootPath": "/dev-api",
    "reload": true,
    "workers": 1,
    "disableSwagger": false,
    "disableRedoc": false,
    "dbType": "mysql",
    "dbHost": "127.0.0.1",
    "dbPort": 3306,
    "dbDatabase": "ruoyi-fastapi",
    "redisHost": "127.0.0.1",
    "redisPort": 6379,
    "logLevel": "INFO",
    "transportCryptoEnabled": false,
    "transportCryptoMode": "off"
  }
}
```

危险命令拒绝样例：

命令：

```bash
ruoyi db revision --env=prod --message="doc-sample" --output=json
```

输出：

```json
{
  "ok": false,
  "message": "生产环境默认禁止直接执行危险命令：db revision",
  "hint": "如确认执行，请传入 --allow-prod；如需跳过确认，请同时传入 --yes"
}
```

`dry-run` 输出样例：

命令：

```bash
ruoyi db upgrade --env=dev --revision=head --dry-run --yes --output=json
```

输出：

```json
{
  "ok": true,
  "message": "数据库已升级到 head（dry-run）",
  "dryRun": true,
  "command": [
    "alembic",
    "-c",
    "/path/to/ruoyi-fastapi-backend/alembic.ini",
    "upgrade",
    "head"
  ],
  "cwd": "/path/to/ruoyi-fastapi-backend"
}
```

代码生成 `dry-run` 文本样例：

命令：

```bash
ruoyi --color=never --icon=none gen export demo_table --env=dev --dry-run --yes --output=text
```

输出：

```text
OK SUCCESS
env: dev
mode: zip
dry_run: true
message: 代码导出演练完成，未执行实际导出
table_names:
  - demo_table
output_file: /path/to/ruoyi-fastapi-backend/gen_code_demo_table.zip
```

代码生成 `dry-run` JSON 样例：

命令：

```bash
ruoyi gen create-table --env=dev --dry-run --yes --sql='CREATE TABLE demo_cli_test (id bigint);' --output=json
```

输出：

```json
{
  "ok": true,
  "message": "建表语句演练完成，未执行实际建表",
  "dryRun": true,
  "statementCount": 1,
  "tableNames": [
    "demo_cli_test"
  ],
  "sql": "CREATE TABLE demo_cli_test (id bigint);",
  "env": "dev"
}
```

参数错误样例：

命令：

```bash
ruoyi --color=never --icon=none gen create-table --env=dev --dry-run --yes --sql='DROP TABLE demo_cli_test;' --output=text
```

输出：

```text
FAIL FAILED
message: 创建表结构失败
error: 建表语句不合法，仅允许 CREATE TABLE 语句
env: dev
```

参数错误 JSON 样例：

命令：

```bash
ruoyi gen create-table --env=dev --dry-run --yes --sql='DROP TABLE demo_cli_test;' --output=json
```

输出：

```json
{
  "ok": false,
  "message": "创建表结构失败",
  "error": "建表语句不合法，仅允许 CREATE TABLE 语句",
  "env": "dev"
}
```

依赖检查失败样例：

说明：

- `app doctor` 和 `ops health` 的返回结果会受到当前数据库、Redis 连通性影响
- 如果依赖不可用，命令会输出失败结果，并返回退出码 `10`

命令：

```bash
ruoyi --color=never --icon=none app doctor --env=dev --output=text
```

输出：

```text
FAIL FAILED
env: dev
checks:
  database: false | 数据库连接失败 | error: <database error message>
  redis: false | Redis连接失败 | error: <redis error message>
  crypto: true | 传输加密配置校验通过
```

命令：

```bash
ruoyi ops health --env=dev --output=json
```

输出：

```json
{
  "env": "dev",
  "database": {
    "ok": false,
    "message": "数据库连接失败",
    "error": "<database error message>",
    "exit_code": 20
  },
  "redis": {
    "ok": false,
    "message": "Redis连接失败",
    "error": "<redis error message>",
    "exit_code": 21
  },
  "ok": false
}
```

### 7.2 退出码

当前统一退出码如下：

- `0`：成功
- `2`：参数错误
- `10`：依赖检查失败
- `20`：数据库失败
- `21`：Redis 失败
- `22`：调度器失败
- `30`：危险操作被拒绝
- `50`：未分类运行错误

## 8. 常见问题

### 8.1 `ruoyi` 命令不可用

请依次确认：

- 当前目录是否为 `ruoyi-fastapi-backend`
- 当前 Python 环境是否执行过 `pip install -r requirements.txt` 或 `pip install -r requirements-pg.txt`
- 当前终端是否真的使用了安装依赖的那个 Python/Conda 环境

### 8.2 命令报数据库或 Redis 连接失败

请检查：

- `.env.*` 中数据库配置是否正确
- `.env.*` 中 Redis 配置是否正确
- 当前网络、容器或主机是否允许连接目标服务
- `app doctor` 与 `ops health` 在依赖异常时返回退出码 `10`
- 单项依赖失败会在 JSON 中带出原始 `error` 和对应依赖退出码

### 8.3 文本输出太花或不适合脚本处理

可以直接切换输出与视觉参数：

```bash
ruoyi --color=never --icon=none ops health --env=dev --output=text
ruoyi ops health --env=dev --output=json
```

### 8.4 使用文档与实现不一致

应以当前 CLI 实现和命令帮助输出为准，并同步更新本文档。
