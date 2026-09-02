# GitHub Actions Workflows

## Docker Build and Push

自动构建 Docker 镜像并推送到 GitHub Container Registry (ghcr.io)。

### 触发条件

- **Push to main/develop**: 推送到主分支或开发分支时自动构建
- **Tag push (v*)**: 推送版本标签时构建（如 v1.0.0）
- **Pull Request**: PR 到 main 分支时构建（不推送）
- **Manual**: 手动触发

### 构建的镜像

所有镜像都会推送到 GitHub Container Registry:

| 镜像 | 用途 | 镜像地址 |
|------|------|----------|
| api | FastAPI 后端服务 | `ghcr.io/[your-org]/prompt-trading-api` |
| worker | 后台任务处理器 | `ghcr.io/[your-org]/prompt-trading-worker` |
| web | React 前端应用 | `ghcr.io/[your-org]/prompt-trading-web` |
| agent | 策略生成容器 | `ghcr.io/[your-org]/prompt-trading-agent` |
| backtest | 回测执行容器 | `ghcr.io/[your-org]/prompt-trading-backtest` |
| dev | 开发环境容器 | `ghcr.io/[your-org]/prompt-trading-dev` |

### 镜像标签策略

- `latest` - 最新的 main 分支构建
- `develop` - develop 分支构建
- `v1.0.0` - 版本号标签
- `v1.0` - 主次版本号
- `v1` - 主版本号
- `main-sha-abc123` - 带 commit SHA 的分支标签

### 首次设置

1. **启用 GitHub Packages**
   - 在仓库的 Settings → Actions → General
   - 确保 "Read and write permissions" 已启用

2. **设置镜像为公开（可选）**
   - 访问 https://github.com/[your-org]?tab=packages
   - 点击每个镜像 → Package settings → Change visibility

3. **在服务器上登录 GHCR**
   ```bash
   # 创建 Personal Access Token (PAT)
   # Settings → Developer settings → Personal access tokens → Tokens (classic)
   # 勾选 read:packages 权限

   echo $PAT | docker login ghcr.io -u USERNAME --password-stdin
   ```

### 使用示例

#### 推送新版本
```bash
git tag v1.0.0
git push origin v1.0.0
```

#### 服务器拉取镜像
```bash
cd infra/compose
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### 本地测试

测试构建（不推送）：
```bash
docker buildx build \
  --platform linux/amd64 \
  -t ghcr.io/your-org/prompt-trading-api:test \
  -f services/api/Dockerfile \
  .
```

### 故障排查

**权限错误**:
```
Error: denied: permission_denied
```
解决：检查 GitHub Actions 权限设置

**镜像太大**:
- 查看 `.dockerignore` 文件
- 使用多阶段构建
- 清理不必要的依赖

**缓存问题**:
```bash
# 在 workflow 中添加
cache-from: type=gha
cache-to: type=gha,mode=max
```

### 监控构建

- 访问仓库的 Actions 标签页
- 查看构建日志和时间
- 检查镜像大小和 layers
