# 传输层加解密配置说明

## 模式说明

`TRANSPORT_CRYPTO_MODE` 共有三种模式：

- `off`
  完全关闭传输层加解密。中间件不执行请求解密与响应加密，前端通过 `/transport/crypto/frontend-config` 获取到的策略也会同步关闭。
- `optional`
  可选加密模式。命中的接口既接受明文请求，也接受加密请求；如果请求已加密，后端会解密后处理，并对命中的 JSON 响应自动加密。适合灰度接入和上线初期观察。
- `required`
  强制加密模式。命中的接口必须携带合法加密信封，明文请求会被直接拒绝；同时防重放校验会按严格模式执行，Redis 不可用时也会拒绝请求。适合链路稳定后的正式强制启用阶段。

补充说明：

- `TRANSPORT_CRYPTO_ENABLED=false` 时，整体效果等同于关闭，不再进入传输层加解密逻辑。
- `TRANSPORT_CRYPTO_ENABLED_PATHS`、`TRANSPORT_CRYPTO_REQUIRED_PATHS` 和 `TRANSPORT_CRYPTO_EXCLUDE_PATHS` 会在上述模式基础上继续约束命中范围。

## 开发环境

开发环境直接使用 `.env.dev` 中默认提供的可用密钥对即可。

说明：

- 传输层加解密启用后，后端启动时必须读到一对匹配的 `TRANSPORT_CRYPTO_PUBLIC_KEY` / `TRANSPORT_CRYPTO_PRIVATE_KEY`。
- 前端会自动读取 `/transport/crypto/frontend-config`，并跟随后端配置完成请求加密、响应解密。
- `/transport/crypto/frontend-config` 和 `/transport/crypto/public-key` 为公开接口，已配置匿名限流，前端会直接调用这两个接口完成初始化。
- `TRANSPORT_CRYPTO_FRONTEND_CONFIG_TTL_SECONDS` 用于控制前端多久重新拉取一次运行策略。
- `TRANSPORT_CRYPTO_PUBLIC_KEY_TTL_SECONDS` 用于控制前端多久重新拉取一次公钥，两者已经独立。

## 生产环境

生产环境使用后端 `.env.prod` 中的密钥配置；仓库默认提供一套可用示例值，正式部署前请替换为正式密钥。

推荐最小配置如下：

```env
TRANSPORT_CRYPTO_ENABLED=true
TRANSPORT_CRYPTO_MODE='optional'
TRANSPORT_CRYPTO_KID='2026-prod-v1'
TRANSPORT_CRYPTO_PUBLIC_KEY='-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n'
TRANSPORT_CRYPTO_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n'
TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS='[]'
TRANSPORT_CRYPTO_FRONTEND_CONFIG_TTL_SECONDS=300
TRANSPORT_CRYPTO_PUBLIC_KEY_TTL_SECONDS=3600
TRANSPORT_CRYPTO_CLOCK_SKEW_SECONDS=120
TRANSPORT_CRYPTO_MAX_GET_URL_LENGTH=4096
```

说明：

- `TRANSPORT_CRYPTO_PUBLIC_KEY` 和 `TRANSPORT_CRYPTO_PRIVATE_KEY` 必须是一对匹配密钥，缺一不可。
- `TRANSPORT_CRYPTO_KID` 表示当前启用的密钥版本。
- `TRANSPORT_CRYPTO_FRONTEND_CONFIG_TTL_SECONDS` 控制 `/transport/crypto/frontend-config` 的前端缓存时长，适合在策略经常调整时适当缩短。
- `TRANSPORT_CRYPTO_PUBLIC_KEY_TTL_SECONDS` 控制 `/transport/crypto/public-key` 的前端缓存时长，主要服务于公钥缓存与密钥轮换。
- `TRANSPORT_CRYPTO_CLOCK_SKEW_SECONDS` 建议控制在 `60-120` 秒，默认收紧为 `120` 秒。
- `TRANSPORT_CRYPTO_REPLAY_TTL_SECONDS` 控制防重放随机数在 Redis 中的有效期；如果准备使用 `required` 模式，建议保证 Redis 稳定可用。
- 初次上线建议先用 `TRANSPORT_CRYPTO_MODE='optional'`，确认链路稳定后再考虑切到 `required`。
- `TRANSPORT_CRYPTO_MAX_GET_URL_LENGTH` 用于限制 GET/DELETE 请求加密后的 URL 长度，前端会通过 `/transport/crypto/frontend-config` 自动同步该值，超限时直接提示改用 POST 或精简查询条件。
- 传输层加密主要面向查询参数、`application/json` 与 `application/x-www-form-urlencoded` 请求；`multipart/form-data` 上传和下载接口默认排除。

## Docker 环境

当前项目的 Docker 部署使用：

- `docker-compose.my.yml` + `Dockerfile.my`
- `docker-compose.pg.yml` + `Dockerfile.pg`

后端容器启动命令分别是：

- `python app.py --env=dockermy`
- `python app.py --env=dockerpg`

所以 Docker 环境需要直接在以下文件中配置传输层密钥：

- `ruoyi-fastapi-backend/.env.dockermy`
- `ruoyi-fastapi-backend/.env.dockerpg`

配置方式与生产环境相同；`.env.dockermy` / `.env.dockerpg` 里也已经默认提供一套可用示例值，正式部署前请替换为正式密钥。

使用时只需要：

1. 修改对应的 `.env.dockermy` 或 `.env.dockerpg`
2. 重新构建并启动 Docker 服务

## 密钥生成

使用 `openssl` 生成一套 RSA 密钥：

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out transport_private.pem
openssl rsa -pubout -in transport_private.pem -out transport_public.pem
```

如果需要写入 `.env`，先转成单行带 `\n` 的格式：

```bash
awk 'NF {sub(/\r/, ""); printf "%s\\\\n",$0;}' transport_private.pem
awk 'NF {sub(/\r/, ""); printf "%s\\\\n",$0;}' transport_public.pem
```

## 使用流程

1. 后端启动时读取当前 `TRANSPORT_CRYPTO_*` 配置，并校验公私钥是否同时存在且彼此匹配。
2. 前端通过 `/transport/crypto/frontend-config` 获取当前运行策略，再通过 `/transport/crypto/public-key` 获取当前 `kid`、协议版本和公钥。
3. `TRANSPORT_CRYPTO_FRONTEND_CONFIG_TTL_SECONDS` 和 `TRANSPORT_CRYPTO_PUBLIC_KEY_TTL_SECONDS` 分别控制这两类缓存的刷新周期。
4. 前端用公钥加密请求，后端用私钥解密请求。
5. 后端会对命中的 JSON 响应自动加密，前端自动解密；下载、上传等排除场景保持明文。

## 密钥轮换

如果需要更换密钥：

1. 生成新密钥对。
2. 修改 `TRANSPORT_CRYPTO_KID` 为新版本，例如 `2026-prod-v2`。
3. 配置新的 `TRANSPORT_CRYPTO_PUBLIC_KEY` 和 `TRANSPORT_CRYPTO_PRIVATE_KEY`。
4. 把旧私钥放入 `TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS`。

补充说明：

- `TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS` 主要用于兼容旧报文解密，最少提供 `kid` 和旧私钥即可；`publicKey` 可选，不填时后端会从私钥推导。
- 轮换期间建议保留旧私钥直到旧公钥缓存全部过期，至少覆盖 `TRANSPORT_CRYPTO_PUBLIC_KEY_TTL_SECONDS` 对应的缓存窗口。

示例：

```env
TRANSPORT_CRYPTO_KID='2026-prod-v2'
TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS='[{"kid":"2026-prod-v1","privateKey":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"}]'
```
