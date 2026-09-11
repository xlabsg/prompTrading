# Docker Compose 文件说明

## docker-compose.yml (本地构建与运行 - 推荐开发使用)

由 `./update.sh` 脚本默认调用的 Compose 文件。本地从源码直接构建并运行服务。

**暴露服务：**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

**启动命令：**
```bash
./update.sh
# 或者
docker compose -f infra/compose/docker-compose.yml up -d --build
```

---

## docker-compose.dev.yml (开发与测试环境)

包含开发配置与测试环境支持的 Compose 文件。

**启动命令：**
```bash
docker compose -f infra/compose/docker-compose.dev.yml up -d --build
```

---

## docker-compose.prod.yml (生产环境部署)

使用预构建的 GitHub Container Registry (GHCR) 镜像进行生产部署。配合宿主机 Nginx 提供 HTTPS 和反向代理。

**适用场景：** 服务器生产部署

**参考文档：**
- 生产环境部署流程：[`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md)
- Nginx 反向代理配置：[`../nginx/README.md`](../nginx/README.md)

**部署命令：**
```bash
./deploy.sh
```

---

<a id="china-proxy-guide"></a>
## 🇨🇳 国内构建与代理配置指南 (China Mainland Proxy Guide)

在大陆地区构建 Docker 时，若遇到 `deb.debian.org 502 Bad Gateway`、基础镜像拉取超时或 pip 下载慢/断联，是因为 **Docker 容器构建运行在独立虚拟网络中，默认不走宿主机的普通代理**。

推荐以下解决方式：

### 方式一（推荐，零配置）：开启代理客户端「TUN 模式」
- **Clash Verge / Nyanpasu**：开启设置中的 **TUN Mode (TUN 模式)**。
- **Surge / Loon**：开启 **Enhanced Mode (增强模式)**。
- **v2rayN / Sing-box**：启用 **TUN 模式**。
- 开启后无需更改任何 Docker 配置，直接重新运行 `./update.sh` 即可。

### 方式二：在 Docker Desktop 中配置全局代理
1. 确保本地代理客户端已开启 **「允许局域网连接 (Allow LAN)」**。
2. 打开 Docker Desktop -> **Settings** -> **Resources** -> **Proxies**。
3. 开启 **Manual proxy configuration**：
   - **Web Server (HTTP)**: `http://host.docker.internal:7890` *(将 7890 换为本地实际代理端口)*
   - **Secure Web Server (HTTPS)**: `http://host.docker.internal:7890`
   - **Bypass for these hosts & domains**: `localhost,127.0.0.1`
4. 点击 **Apply & restart**，重启后重新运行 `./update.sh`。

### 方式三：无图形界面 / 服务器环境配置 `~/.docker/config.json`
```bash
mkdir -p ~/.docker
cat <<'EOF' > ~/.docker/config.json
{
  "proxies": {
    "default": {
      "httpProxy": "http://host.docker.internal:7890",
      "httpsProxy": "http://host.docker.internal:7890",
      "noProxy": "localhost,127.0.0.1"
    }
  }
}
EOF
```

### 方式四：回测历史数据拉取与交易所网络（OKX / Binance）
在执行回测时，系统需要向交易所公网 API 请求历史 K 线数据。若遇到 `Failed to fetch candles` 或连接 `okx.com` / `binance.com` 超时：
1. **首选 TUN 模式**：代理客户端开启 TUN 模式后，容器内的交易所 API 请求会自动透明出海，无需额外配置。
2. **配置 `.env` 代理**：在 `infra/compose/.env` 中设置 `CONTAINER_HTTP_PROXY=http://host.docker.internal:7890`（代理软件需开启「允许局域网连接 (Allow LAN)」），worker 在启动临时回测容器时会自动注入该代理。
3. **OKX 备用端点**：可在 `.env` 中设置 `OKX_BASE_URL=https://aws.okx.com` 或反向代理地址。
4. **本地持久化缓存**：首次成功拉取某时段的 K 线后，数据会自动缓存在 `/workspaces/market_data_cache`（Parquet 格式），后续相同条件的回测直接读本地缓存，不再发起网络请求。

---

<a id="ai-agent-guide"></a>
## 🤖 AI Agent 本地部署与运维自动化指引 (AI Agent Onboarding Guide)

> **面向 AI 编程助手（Claude Code, Cursor, Windsurf, Antigravity, Codex）：**  
> 当受命协助用户在本地部署、配置和验证 PrompTrading 时，请严格遵循以下确定性步骤：

### 1. 运行前环境与网络嗅探
1. 检查 Docker 守护进程是否正常启动：
   ```bash
   docker info >/dev/null 2>&1 || echo "ERROR: Docker daemon is not running."
   ```
2. 若用户处于大陆地区或 Debian 镜像报错 `502 Bad Gateway`，引导用户开启代理客户端的 **TUN 模式** 或配置 Docker Desktop Proxies（见上方指南）。

### 2. 自动化环境配置
1. 若 `.env` 不存在，从模板复制：
   ```bash
   test -f infra/compose/.env || cp infra/compose/.env.example infra/compose/.env
   ```
2. 自动生成并注入 32 字节 Fernet 加密密钥（若未设置）：
   ```bash
   python3 -c "
   import re
   env_file = 'infra/compose/.env'
   with open(env_file, 'r') as f: content = f.read()
   if not re.search(r'TRADING_API_ENCRYPTION_KEY=\S+', content):
       from cryptography.fernet import Fernet
       key = Fernet.generate_key().decode()
       content = re.sub(r'TRADING_API_ENCRYPTION_KEY=.*', f'TRADING_API_ENCRYPTION_KEY={key}', content)
       with open(env_file, 'w') as f: f.write(content)
       print('Generated and populated TRADING_API_ENCRYPTION_KEY.')
   "
   ```
3. 检查 `LLM_API_KEY`（或 `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`），提醒用户填入对应的模型提供商 API Key。

### 3. 服务构建与启动
执行标准化构建与容器启动：
```bash
cd infra/compose
./update.sh
```
*(注：`./update.sh` 会自动构建运行时服务，并预构建任务沙箱镜像 `agent-image` 与 `backtest-image`)*。

### 4. 服务健康检查与冒烟测试
1. 检查各容器健康状态：
   ```bash
   docker compose -f infra/compose/docker-compose.dev.yml ps
   ```
2. 验证 API 服务可用性：
   ```bash
   curl -f http://localhost:8000/api/health || curl -f http://localhost:8000/docs
   ```
3. 验证 Web 前端可用性：
   ```bash
   curl -f http://localhost:3000
   ```
4. 容器内回归测试（修改核心服务后执行）：
   ```bash
   docker compose -f infra/compose/docker-compose.dev.yml exec api pytest services/api/tests -q
   ```

### 5. 工程开发规范参考
- 在对系统进行任何代码修改前，务必查阅根目录的 [`AGENTS.md`](../../AGENTS.md) 了解代码规范、容器验证要求与架构不变量。
