# RuoYi-FastAPI Vue2 移动端

基于 `uni-app` 的 `vue2` + `tailwindcss` 开发。

## 快速开始

本工程位于 `ruoyi-fastapi-frontend/vue2/mobile`，与同仓库 Vue2/Vue3 Web 和 Vue3 移动端共用 `ruoyi-fastapi-backend`。从仓库根目录执行：

```bash
cd ruoyi-fastapi-frontend/vue2/mobile
yarn install
yarn dev:h5
```

后续命令均在本工程目录执行。后端地址在 `src/config.js` 的 `baseUrl` 中配置；真机或模拟器运行时需使用设备可访问的后端地址。

> 本项目已经集成 `weapp-ide-cli` 可以通过 `cli` 对 `ide` 进行额外操作，[详细信息](https://www.npmjs.com/package/weapp-ide-cli)

### 构建小程序

```bash
yarn dev:mp-weixin
```

### 打开微信开发者工具

> 需要打开开发者工具，设置，安全中的服务端口选项

```bash
yarn open:dev
```

## Tips

- 使用 `npx @dcloudio/uvm` 升级 `uni-app` 依赖
