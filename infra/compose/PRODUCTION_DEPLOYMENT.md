# 生产环境部署指南

## 概述

本指南介绍如何使用 GitHub Actions 自动构建 Docker 镜像，并在生产服务器上部署。

## 架构

```
GitHub Repository
    ↓ (push/tag)
GitHub Actions (自动构建)
    ↓ (push images)
GitHub Container Registry (ghcr.io)
    ↓ (pull images)
生产服务器 (docker compose)
```

## 第一步：配置 GitHub Actions

### 1.1 启用 GitHub Packages 权限

1. 访问仓库的 **Settings → Actions → General**
2. 在 "Workflow permissions" 部分
3. 选择 **"Read and write permissions"**
4. 勾选 **"Allow GitHub Actions to create and approve pull requests"**
5. 点击 Save

### 1.2 触发首次构建

```bash
# 方式 1: 推送到 main 分支
git push origin main

# 方式 2: 创建版本标签
git tag v1.0.0
git push origin v1.0.0

# 方式 3: 手动触发
# 访问 Actions 标签页 → Build and Push Docker Images → Run workflow
```

### 1.3 查看构建状态

访问仓库的 **Actions** 标签页，查看构建进度。

## 第二步：配置镜像访问权限

### 2.1 设置镜像为公开（推荐用于开源项目）

1. 访问 https://github.com/[your-org]?tab=packages
2. 点击每个镜像（api, worker, web, agent, backtest）
3. 进入 **Package settings**
4. 点击 **Change visibility** → **Public**

### 2.2 或创建私有访问 Token（用于私有镜像）

1. 访问 **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. 点击 **Generate new token (classic)**
3. 设置以下权限：
   - ✅ `read:packages` - 读取包
   - ✅ `write:packages` - 写入包（如果需要推送）
4. 生成并**保存 token**（只显示一次！）

## 第三步：服务器配置

### 3.1 登录到 GitHub Container Registry

**如果镜像是公开的**：
```bash
# 可以跳过此步骤，直接拉取
docker pull ghcr.io/your-org/prompt-trading-api:latest
```

**如果镜像是私有的**：
```bash
# 使用 Personal Access Token 登录
echo $YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# 验证登录
docker pull ghcr.io/your-org/prompt-trading-api:latest
```

### 3.2 克隆仓库（或只下载配置文件）

```bash
# 方式 1: 克隆完整仓库
git clone https://github.com/your-org/prompTrading.git
cd prompTrading/infra/compose

# 方式 2: 只下载需要的文件
mkdir -p ~/prompt-trading-deploy
cd ~/prompt-trading-deploy
curl -O https://raw.githubusercontent.com/your-org/prompTrading/main/infra/compose/docker-compose.prod.yml
curl -O https://raw.githubusercontent.com/your-org/prompTrading/main/infra/compose/.env.example
curl -O https://raw.githubusercontent.com/your-org/prompTrading/main/infra/compose/deploy.sh
chmod +x deploy.sh
```

### 3.3 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量
nano .env
```

**必填变量**：
```bash
# GitHub Container Registry
GITHUB_ORG=your-github-org        # 你的 GitHub 组织或用户名（小写）
IMAGE_TAG=latest                   # 或 v1.0.0, develop 等

# 应用 URL
APP_PUBLIC_BASE_URL=https://ai.example.com

# 交易加密密钥（生成方法见下方）
TRADING_API_ENCRYPTION_KEY=
```

**生成加密密钥**：
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3.4 首次部署

```bash
# 使用部署脚本（推荐）
./deploy.sh

# 或手动部署
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## 第四步：验证部署

### 4.1 检查服务状态

```bash
# 查看所有服务
docker compose -f docker-compose.prod.yml ps

# 查看服务日志
docker compose -f docker-compose.prod.yml logs -f

# 查看特定服务日志
docker compose -f docker-compose.prod.yml logs -f api
```

### 4.2 健康检查

```bash
# API 健康检查
curl http://localhost:8000/health

# Frontend 检查
curl http://localhost:3000

# 查看 API 文档
open http://localhost:8000/docs
```

### 4.3 查看资源使用

```bash
# 实时资源监控
docker stats

# 查看磁盘使用
docker system df
```

## 日常运维

### 更新到最新版本

```bash
# 方式 1: 使用部署脚本（推荐）
./deploy.sh

# 方式 2: 手动更新
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### 更新到特定版本

```bash
# 1. 修改 .env 文件
nano .env
# 设置 IMAGE_TAG=v1.2.3

# 2. 重新部署
./deploy.sh
```

### 回滚到上一版本

```bash
# 1. 修改 .env 文件中的 IMAGE_TAG
IMAGE_TAG=v1.0.0  # 改为上一个稳定版本

# 2. 重新部署
./deploy.sh
```

### 查看日志

```bash
# 所有服务日志
docker compose -f docker-compose.prod.yml logs -f

# 特定服务日志（最近 100 行）
docker compose -f docker-compose.prod.yml logs --tail=100 api

# 实时跟踪日志
docker compose -f docker-compose.prod.yml logs -f api worker
```

### 重启服务

```bash
# 重启所有服务
docker compose -f docker-compose.prod.yml restart

# 重启特定服务
docker compose -f docker-compose.prod.yml restart api

# 停止并重新创建
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### 清理资源

```bash
# 清理未使用的镜像
docker image prune -a

# 清理所有未使用的资源
docker system prune -a --volumes

# 查看磁盘空间
docker system df
```

## 高级配置

### 使用 Nginx 反向代理

参考 [infra/nginx/README.md](../nginx/README.md) 配置 Nginx。

### 监控和日志

```bash
# 安装 Prometheus + Grafana（可选）
# docker-compose.monitoring.yml

# 集中日志（可选）
# 使用 ELK Stack 或 Loki
```

### 备份数据

```bash
# 备份 Workspaces 数据卷（包含 SQLite 数据库 app.db 与策略文件）
docker run --rm \
  -v ai_strategy_workspaces:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/workspaces_$(date +%Y%m%d).tar.gz /data

# 若配置了外部 PostgreSQL (APP_DB_URL):
# pg_dump "$APP_DB_URL" > backup_$(date +%Y%m%d).sql
```

### 恢复数据

```bash
# 恢复 Workspaces 数据卷
docker run --rm \
  -v ai_strategy_workspaces:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/workspaces_YYYYMMDD.tar.gz --strip-components=1"
```

## 故障排查

### 服务启动失败

```bash
# 查看详细错误
docker compose -f docker-compose.prod.yml logs api

# 检查配置
docker compose -f docker-compose.prod.yml config

# 验证环境变量
docker compose -f docker-compose.prod.yml exec api env
```

### 镜像拉取失败

```bash
# 问题: denied: permission denied
# 解决: 重新登录 GHCR
echo $PAT | docker login ghcr.io -u USERNAME --password-stdin

# 问题: 镜像不存在
# 解决: 检查 GITHUB_ORG 和 IMAGE_TAG 是否正确
cat .env | grep -E "GITHUB_ORG|IMAGE_TAG"
```

### 数据库连接失败

```bash
# 测试数据库连接（默认 SQLite 或通过 APP_DB_URL 指定的数据库）
docker compose -f docker-compose.prod.yml exec api \
  python -c "from sqlalchemy import create_engine; import os; engine = create_engine(os.getenv('APP_DB_URL', 'sqlite:////workspaces/app.db')); print(engine.connect())"
```

### 内存不足

```bash
# 查看内存使用
docker stats --no-stream

# 限制容器内存（修改 docker-compose.prod.yml）
services:
  api:
    deploy:
      resources:
        limits:
          memory: 1G
```

## 安全检查清单

- [ ] 妥善保管数据库文件及连接凭据
- [ ] 生成新的 TRADING_API_ENCRYPTION_KEY
- [ ] 配置防火墙（只开放 80, 443, 22 端口）
- [ ] 使用 HTTPS（配置 Nginx + Let's Encrypt）
- [ ] 定期更新镜像（`./deploy.sh`）
- [ ] 启用日志轮转
- [ ] 定期备份数据库
- [ ] 监控磁盘空间
- [ ] 设置资源限制（CPU, Memory）

## 参考资源

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [GitHub Container Registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Nginx 部署指南](../nginx/README.md)
