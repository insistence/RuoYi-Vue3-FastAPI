# 更新日志

## RuoYi-Vue3-FastAPI v1.9.0

### 项目依赖

前后端依赖均有升级，请升级依赖或重新创建环境。

### 新增功能

1.新增AI管理模块 ([#69](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/69))。
2.新增移动端模块 ([#73](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/73))。
3.新增多worker运行支持 ([#76](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/76))。
4.应用新增演示模式 ([#78](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/78))。

### BUG修复

1.修复代码生成controller模板删除接口query_db参数异常的问题 ([#63](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/63))。
2.修复登录接口response_model声明错误 ([#71](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/71))。
3.修复无法直接通过后端地址访问API文档的问题 ([#74](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/74))。
4.修复create_app重复执行的问题 ([#84](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/84))。

### 代码重构

1.移除对python3.9的支持 ([#67](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/67))。

### 代码优化

1.优化alembic处理表模型逻辑，避免无关表影响 ([#68](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/68))。
2.优化代码生成后端模板 ([#72](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/72))。
3.自动注册路由出错时抛出异常以便于调试 ([#79](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/79))。
4.优化部分页面字段tooltip说明 (#80)。
5.优化项目启动速度 ([#82](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/82))。
6.优化暗黑模式切换效果 ([#83](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/83))。
7.优化热重载模式或单worker下scheduler的任务状态同步机制 ([#85](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/85))。
8.优化防重提交间隔时间可自定义 ([#87](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/87))。
9.优化验证码计算结果为非负数 ([#88](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/88))。
10.优化ci测试稳定性 ([#90](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/90))。

## RuoYi-Vue3-FastAPI v1.8.1

### 新增功能

1.新增E2E测试 ([#57](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/57))。

### BUG修复

1.修复DictTag组件渲染异常的问题 ([#59](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/59))。

### 代码优化

1.优化数据权限依赖 ([#55](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/55))。
2.动态导入定时任务函数，移除eval ([#56](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/56))。
3.优化pg版本的docker compose配置文件 ([#61](https://github.com/insistence/RuoYi-Vue3-FastAPI/pull/61))。

## RuoYi-Vue3-FastAPI v1.8.0

### 项目依赖

#### 后端

1.后端依赖升级到最新版本，请升级依赖或重新创建环境。

### 新增功能

1.新增请求上下文管理类。
2.新增`PreAuthDependency`、`CurrentUserDependency`、`DataScopeDependency`、`DBSessionDependency`、`UserInterfaceAuthDependency`和`RoleInterfaceAuthDependency`依赖函数。
3.新增上下文清理中间件。
4.新增公共vo模块。
5.新增配置文档静态资源方法。
6.新增自动注册路由功能。
7.新增docker compose部署方式。
8.菜单导航设置支持纯顶部。

### BUG修复

1.修复单账号登录模式下强退功能失效的问题 [#52](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/52)。
2.确保ApschedulerJobs字段类型与apscheduler默认创建的表字段类型一致 [#53](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/53)。
3.修复磁盘存在异常时服务监控无法正常运行的问题。
4.移除代码生成表业务表外键，修复无法删除的问题。
5.修复固定头部时出现的导航栏偏移问题。
6.修复表单构建移除所有控件后切换路由回来空白问题。
7.修复代码生成v3模板时间控件between选择后清空报错问题。

### 代码重构

1.增强ruff规则，完善类型提示。
2.优化项目结构，新增common模块，原annotation、aspect、constant、enums模块移动至common模块下。
3.重构app与server设计。

### 代码优化

1.controller层全部使用新依赖项。
2.当前用户信息使用上下文变量。
3.分页模型改为使用公共vo模块的PageModel。
4.优化API文档的响应模型显示。
5.操作响应模型改为使用公共vo模块的CrudResponseModel。
6.优化API文档的接口描述信息。
7.登录/注册页面底部版权信息修改为读取配置。
8.优化生成代码下载的zip文件名。
9.优化表单构建关闭页签销毁复制插件。
10.行内表单默认设置固定宽度。
11.优化操作日志详细请求参数显示。
12.优化index页面标题读取配置。
13.优化字典组件数字类型值处理逻辑。
14.优化字典组件值宽松匹配。
15.默认固定头部。

## RuoYi-Vue3-FastAPI v1.7.1

### 项目依赖

1.后端依赖移除passlib，直接使用bcrypt。

### BUG修复

1.修复代码生成controller模板编辑接口异常生成字段的问题。
2.移除passlib直接使用bcrypt修复密码校验异常的问题 [#48](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/48) [#49](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/49)。

### 代码优化

1.代码生成do模板补充表描述。

## RuoYi-Vue3-FastAPI v1.7.0

### 项目依赖

1.前后端依赖升级，请升级依赖或重新创建环境。

### 新增功能

1.新增alembic支持。
2.文件&图片上传组件支持自定义地址&参数。
3.新增默认打包配置项。
4.显隐列组件支持全选/全不选。
5.添加页签openPage支持传递参数。
6.外链加载时遮罩信息提示。
7.上传组件新增拖动排序属性。
8.图片上传组件新增disabled属性。
9.代码生成列支持拖动排序。
10.新增用户默认初始化密码。
11.新增页签图标显示开关功能。
12.新增底部版权信息及开关。
13.用户归属部门新增清除。
14.用户导入新增验证提示。
15.菜单搜索支持键盘选择&悬浮主题背景。
16.新增apscheduler_jobs表对应sqlalchemy模型类。
17.初始密码支持自定义修改策略。
18.账号密码支持自定义更新周期。
19.注册账号设置默认密码最后更新时间。
20.显示列信息支持对象格式。

### BUG修复

1.修复logout接口未按照app_same_time_login配置项动态判断的问题 [#IBZZ1S](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/IBZZ1S)。
2.修复上传组件被多次引用拖动仅对第一个有效的问题。

### 代码优化

1.优化接口耗时计算。
2.优化启动信息显示。
3.优化前端处理路由函数代码。
4.登录页和注册页表头使用VITE_APP_BASE_API配置值。
5.优化角色禁用不允许分配。
6.优化富文本控制台警告异常。
7.优化checkbox废弃API。
8.优化导航栏显示昵称&设置。

### 代码重构

1.重构IP归属区域查询为异步调用。
2.调整do与sql使其相互适配以支持alembic。
3.富文本复制粘贴图片上传至url。

## RuoYi-Vue3-FastAPI v1.6.2

### 新增功能

1.文件上传组件新增disabled属性。
2.文件上传组件新增类型。

### BUG修复

1.修复日志管理时间查询报错 [#27](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/27)。
2.修复定时任务状态暂停时执行单次任务会触发cron表达式的问题 [#31](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/31)。
3.修复修改字典类型时获取dict_code异常的问题。
4.修复修改字典类型时字典数据更新时间异常的问题。
5.修复代码生成模板时间查询问题 [#28](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/28)。
6.修复用户导出缺失部门名称的问题。

### 代码优化

1.优化代码生成新增和编辑字段显示和渲染。
2.pagination更换成flex布局。
3.优化代码生成vue模板 [#23](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/23)。

## RuoYi-Vue3-FastAPI v1.6.1

### 项目依赖

#### 后端

1.新增sqlglot依赖

```bash
pip install sqlglot[rs]==26.6.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### BUG修复

1.引入sqlglot修复sql语句解析异常的问题。
2.修复代码生成字段唯一性校验dao层模板判断异常的问题。
3.引入泛型修复as_query和as_form装饰模型文档丢失的问题。
4.修复代码生成主子表vo模板可能缺失NotBlank的问题。

## RuoYi-Vue3-FastAPI v1.6.0

### 项目依赖

1.后端依赖升级到最新版本，请升级依赖或重新创建环境。

### 新增功能

1.新增代码生成功能，支持配置数据库表信息一键生成和下载前后端代码，需要重新执行sql文件，请先备份数据。
2.新增表单构建功能。
3.用户头像新增支持http(s)链接。
4.新增trace中间件强化日志链路追踪和响应头 [@y1ren](https://gitee.com/y1ren)。
5.用户管理支持分栏拖动。
6.菜单面包屑导航支持多层级显示。
7.白名单支持对通配符路径匹配。
8.支持开启暗黑模式。

### BUG修复

1.修复默认关闭Tags-Views时，内链页面打不开。
2.修复删除当前登录用户拦截失效的问题。
3.修复定时任务目标字符串规则校验不全的问题。
4.修复执行单次任务时会覆盖已启用任务的问题 [#IBEKD2](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/IBEKD2)。
5.修复个人中心特殊字符密码修改失败问题。

### 代码优化

1.优化导出方法。
2.参数键值更换为多行文本。
3.优化日志中操作方法显示。
4.优化日志装饰器获取核心参数的方式。
5.用户管理过滤掉已禁用部门。
6.优化TopNav内链菜单点击没有高亮。
7.ResponseUtil补充完整参数。

## RuoYi-Vue3-FastAPI v1.5.1

### 新增功能

1.定时任务新增支持调用异步函数。

### 代码优化

1.优化字典数组条件判断。
2.校检文件名是否包含特殊字符。
3.移除已弃用的log_decorator装饰器。

## RuoYi-Vue3-FastAPI v1.5.0

### 新增功能

1.新增对PostgreSQL数据库的支持。

### BUG修复

1.修复DictTag组件控制台抛异常的问题 [#IAYSVZ](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/IAYSVZ)。
2.修复登录日志导出文件名称错误的问题。

### 代码回滚

1.因fastapi查询参数模型底层存在bug，回滚查询参数模型声明方式为as_query。

### 代码优化

1.优化CamelCaseUtil和SnakeCaseUtil以兼容更多转换场景。
2.优化列表查询排序。
3.优化参数设置页面。
4.优化上传图片带域名时不增加前缀。

## RuoYi-Vue3-FastAPI v1.4.0

### 项目依赖

#### 后端

1.更新fastapi版本为0.115.0

```bash
pip install fastapi[all]==0.115.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 代码重构

1.基于fastapi 0.115.0版本新特性，直接使用pydantic模型接收查询参数和表单数据，移除原有as_query和as_form使用方式。

### BUG修复

1.修复角色管理service书写错误。

### 代码优化

1.优化前端登录请求方法。

## RuoYi-Vue3-FastAPI v1.3.3

### 项目依赖

#### 后端

1.更新pydantic-validation-decorator版本为0.1.4，修复了一些底层bug。

### BUG修复

1.修复在线用户模块条件查询无效的问题。

### 代码优化

1.优化在线用户模块前后端字段描述一致。
2.日志装饰器异常处理增加logger打印日志。

## RuoYi-Vue3-FastAPI v1.3.2

### 新增功能

1.新增gzip压缩中间件。

### BUG修复

1.修复分页函数计算has_next错误的问题 [#10](https://github.com/insistence/RuoYi-Vue3-FastAPI/issues/10)。
2.修复定时任务监听函数中事件没有job_id报错的问题。

### 代码优化

1.优化添加中间件函数注释。

## RuoYi-Vue3-FastAPI v1.3.1

### BUG修复

1.修复1.3.0版本采用新的异常处理机制后日志装饰器无法记录异常日志的问题。

### 代码优化

1.补充定时任务违规字符串。

## RuoYi-Vue3-FastAPI v1.3.0

### 项目依赖

1.前后端依赖均升级到最新版本，请升级依赖或重新创建环境。
2.使用`PyJWT`替换`python-jose`以解决一些安全性问题。

### 新增功能

1.新增字段校验装饰器，支持手动触发校验，已封装为`pydantic-validation-decorator`库。
2.各模块`service`层新增字段唯一性校验。
3.全局新增`ServiceException`自定义服务异常和`ServiceWarning`自定义服务警告，无需在接口中写大量的异常捕获。
4.菜单管理新增路由名称，请执行以下sql为数据库新增字段：

```sql
ALTER TABLE sys_menu ADD COLUMN route_name varchar(50) DEFAULT '';
```

5.新增`constant`常量配置及`enums`枚举类型配置。
6.新增`StringUtil`、`CronUtil`工具类。

### BUG修复

1.修复用户管理、角色管理、部门管理越权漏洞。
2.修复各模块`dao`层`status`、`del_flag`类型与数据库不一致的问题。
3.修复移动端左侧菜单无法显示的问题。
4.修复其他已知BUG。

### 代码重构

1.重构日志装饰器为`Log`，未来版本将删除`log_decorator`装饰器，请尽快迁移。
2.重构`RedisInitKeyConfig`为枚举类型，现在可通过以下方式获取对应的`key`和`remark`
`RedisInitKeyConfig.ACCESS_TOKEN.key`、`RedisInitKeyConfig.ACCESS_TOKEN.remark`。
3.重构数据权限逻辑，底层进行优化，使用方法与之前相同。

### 代码优化

1.引入`ruff`对后端代码进行格式化及检测修复，优化导入。
2.各模块基于`ServiceException`自定义服务异常和`ServiceWarning`自定义服务警告优化了异常处理逻辑。
3.各模块`vo`层使用`Field`声明字段。
4.优化API文档字段描述显示。

## RuoYi-Vue3-FastAPI v1.2.2

### BUG修复

1.修复删除定时任务时未移除调度中任务的问题。
2.修复菜单生成路由时组件条件判断错误的问题。

## RuoYi-Vue3-FastAPI v1.2.1

### BUG修复

1.修复各模块新增数据时创建时间记录异常的问题。
2.修复菜单挂载到根目录时路由加载异常等一系列相关问题。

### 代码及性能优化

1.修改代理localhost为127.0.0.1以适配部分设备解析localhost异常的问题。

## RuoYi-Vue3-FastAPI v1.2.0

### 重要说明

本次更新为 **_破坏性更新_** ，重构数据库orm为异步，代码改动很大，请谨慎升级。
1.原有的Session类型声明统一变更为AsyncSession。
2.service层和dao层的函数修改为异步函数，请使用await调用。
3.orm查询不再支持query，请使用select、update、delete等语句，具体使用方法请参考[https://docs.sqlalchemy.org/en/20/orm/queryguide/index.html](https://docs.sqlalchemy.org/en/20/orm/queryguide/index.html)。

### 项目依赖

#### 后端

1.增加asyncmy依赖用于支持orm异步操作mysql，请重新安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple。
```

### 新增功能

1.新增SnakeCaseUtil工具类，将原CamelCaseUtil工具类的camel_to_snake函数迁移至SnakeCaseUtil工具类。

### BUG修复

1.修复用户管理模块重置用户密码时会异常重置用户岗位和角色的问题。
2.修复清空定时任务日志异常的问题。

## RuoYi-Vue3-FastAPI v1.1.3

### 新增功能

1.用户密码新增非法字符验证。

### BUG修复

1.修复通知公告列表查询前后端字段不一致的问题。
2.修复个人中心修改基本资料后端异常的问题。

## RuoYi-Vue3-FastAPI v1.1.2

### 新增功能

1.配置文件新增数据库连接池相关配置。

### BUG修复

1.修复个人中心修改密码后端异常的问题。

### 代码及性能优化

1.使用@lru_cache缓存ip归属区域查询结果，避免重复调用ip归属区域查询接口以优化性能。

## RuoYi-Vue3-FastAPI v1.1.1

### BUG修复

1.修复编辑定时任务时更新的信息未同步至scheduler的问题 [#I9EK56](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I9EK56)。
2.修复编辑角色数据权限时后端异常的问题 [#I9ENQN](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I9ENQN)。
3.修复菜单配置路由参数不生效的问题。
4.修复获取路由信息时菜单排序不生效的问题。
5.修复添加菜单时是否外链和是否缓存回显异常的问题。

## RuoYi-Vue3-FastAPI v1.1.0

### 新增功能

1.后端配置文件新增sqlalchemy日志开关配置。
2.后端配置文件新增IP归属区域查询开关配置。
3.后端配置文件新增账号同时登录开关配置。

### BUG修复

1.修复token本身过期时退出登录接口异常的问题 [#I9CBWT](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I9CBWT)。
2.修复系统版本号或浏览器版本号无法获取时登录异常的问题 [#I9CYNM](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I9CYNM)。

## RuoYi-Vue3-FastAPI v1.0.3

### 新增功能

1.账号密码登录新增IP黑名单校验。

### BUG修复

1.修复外链菜单无法打开的问题 [#I95KBK](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I95KBK)。
2.修复添加和编辑菜单页面中是否缓存和是否外链字段回显异常的问题 [#I95KBK](https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI/issues/I95KBK)。

## RuoYi-Vue3-FastAPI v1.0.2

### 新增功能

1.用户接口权限校验增加列表接收参数，实现同一接口支持多个权限标识校验。
2.新增按角色校验接口权限依赖

### BUG修复

1.修复用户管理和部门管理模块数据权限异常的问题。

### 代码及性能优化

1.调整参数设置、部门管理、字典管理、定时任务、日志管理、角色管理、菜单管理模块部分接口权限标识。

## RuoYi-Vue3-FastAPI v1.0.1

### 项目依赖

#### 后端

1.更新fastapi版本为0.109.1，修复一些安全性问题，命令：

```bash
pip install fastapi[all]==0.109.1 -i https://mirrors.aliyun.com/pypi/simple/
```

### 新增功能

1.日志管理模块新增字段排序查询。

## RuoYi-Vue3-FastAPI v1.0.0

RuoYi-Vue3-FastAPI第一个版本发布啦！
此版本功能如下：
1.用户管理：用户是系统操作者，该功能主要完成系统用户配置。
2.角色管理：角色菜单权限分配。
3.菜单管理：配置系统菜单，操作权限，按钮权限标识等。
4.部门管理：配置系统组织机构（公司、部门、小组）。
5.岗位管理：配置系统用户所属担任职务。
6.字典管理：对系统中经常使用的一些较为固定的数据进行维护。
7.参数管理：对系统动态配置常用参数。
8.通知公告：系统通知公告信息发布维护。
9.操作日志：系统正常操作日志记录和查询；系统异常信息日志记录和查询。
10.登录日志：系统登录日志记录查询包含登录异常。
11.在线用户：当前系统中活跃用户状态监控。
12.定时任务：在线（添加、修改、删除）任务调度包含执行结果日志。
13.服务监控：监视当前系统CPU、内存、磁盘、堆栈等相关信息。
14.缓存监控：对系统的缓存信息查询，命令统计等。
15.系统接口：根据业务代码自动生成相关的api接口文档。
