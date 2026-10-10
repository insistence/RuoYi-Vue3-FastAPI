# 构建阶段
FROM node:18-slim AS builder
ENV TZ=UTC
ENV NODE_OPTIONS=--openssl-legacy-provider
WORKDIR /app

# 复制源代码
COPY . .

# 设置npm镜像源
RUN npm config set registry https://registry.npmmirror.com

# 仓库不提交 npm 锁文件，Vue CLI 4 使用旧版 webpack 依赖。
RUN npm install --legacy-peer-deps --no-package-lock

# 执行docker构建命令
RUN npm run build:docker

# 运行阶段
FROM nginx:latest
ENV TZ=UTC
WORKDIR /usr/share/nginx/html

# 复制构建产物
COPY --from=builder /app/dist .

# 暴露端口
EXPOSE 80

# 启动nginx
CMD ["nginx", "-g", "daemon off;"]
