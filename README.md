# 内置功能
1. 用户管理：用户是系统操作者，该功能主要完成系统用户配置。
2. 角色管理：角色菜单权限分配、设置角色按机构进行数据范围权限划分。
3. 菜单管理：配置系统菜单，操作权限，按钮权限标识等。
4. 部门管理：配置系统组织机构（公司、部门、小组）。
5. 岗位管理：配置系统用户所属担任职务。
6. 字典管理：对系统中经常使用的一些较为固定的数据进行维护。
7. 参数管理：对系统动态配置常用参数。
8. 通知公告：系统通知公告信息发布维护。
9. 操作日志：系统正常操作日志记录和查询；系统异常信息日志记录和查询。
10. 登录日志：系统登录日志记录查询包含登录异常。
11. 在线用户：当前系统中活跃用户状态监控。
12. 定时任务：在线（添加、修改、删除）任务调度包含执行结果日志。
13. 服务监控：监视当前系统CPU、内存、磁盘、堆栈等相关信息。
14. 缓存监控：对系统的缓存信息查询，命令统计等。
15. 传输加密：支持前后端请求加密、响应解密、公钥轮换、运行策略下发与监控统计。
16. 在线构建器：拖动表单元素生成相应的HTML代码。
17. 系统接口：根据业务代码自动生成相关的api接口文档。
18. 代码生成：配置数据库表信息一键生成前后端代码（python、sql、vue、js），支持下载。
19. AI管理：提供AI模型管理和AI对话功能。

# 前端
```bash
# 进入前端目录
cd ruoyi-fastapi-frontend

# 安装依赖
pnpm install

# 启动服务
npm run dev
```

发布
```bash
# 构建测试环境
pnpm run build:stage 

# 构建生产环境
pnpm run build:prod 
```

# 移动端
```bash
# 进入移动端目录
cd ruoyi-fastapi-app

# 安装依赖
pnpm install

# 启动 H5
pnpm dev:h5

# 启动微信小程序
pnpm dev:mp-weixin
```

# 后端
```bash
# 进入后端目录
cd ruoyi-fastapi-backend

pip3 install -r requirements-pg.txt

# 配置环境
在.env.dev文件中配置开发环境的数据库和redis

# 运行sql文件
1.新建数据库ruoyi-fastapi(默认，可修改)
2.使用命令或数据库连接工具运行sql文件夹下的ruoyi-fastapi-pg.sql

# 运行后端
ruoyi app run --env=dev
```

发布
```bash
# 配置环境
在.env.prod文件中配置生产环境的数据库和redis

# 运行后端
ruoyi app run --env=prod
```

### Docker Compose部署方式
```bash
docker compose -f docker-compose.pg.yml up -d --build
```
**警告：** 默认未做数据持久化配置，请注意数据备份或自行配置持久化


# 访问
```bash
# 默认账号密码
账号：admin
密码：admin123

# 浏览器访问
地址：http://localhost:5173
```

# 交流与赞助
扫描下面微信二维码添加微信备注RuoYi-FastAPI即可进群。

<!-- 使用HTML表格实现并排显示 -->
<table>
  <tr>
    <!-- 第一个图片：个人二维码 -->
    <td style="text-align:center; padding:10px;">
      <img src="https://github.com/user-attachments/assets/c73b2dd6-c3aa-4675-b166-99ba4675c80e" alt="个人二维码" width="300" />
      <br>
      <small>个人二维码</small>
    </td>
    <!-- 第二个图片：个人收款码 -->
    <td style="text-align:center; padding:10px;">
      <img src="https://github.com/user-attachments/assets/bba951cf-9319-4bf3-a9c4-db9b9e1e69c4" alt="个人收款码" width="300" />
      <br>
      <small>个人收款码</small>
    </td>
  </tr>
</table>







