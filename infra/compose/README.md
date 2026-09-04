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

