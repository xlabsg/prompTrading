# Docker Compose 文件说明

## docker-compose.dev.yml (开发环境 - 推荐使用)

**特点：**
- ✅ 简化配置，直接暴露端口
- ✅ 无需 Traefik 反向代理
- ✅ 直接访问服务：
  - Frontend: http://localhost:3000
  - API: http://localhost:8000
  - Postgres: localhost:5432
  - Redis: localhost:6379

**适用场景：** 本地开发、测试


## docker-compose.yml (生产环境)

**特点：**
- 包含 Traefik 反向代理
- 通过代理访问服务（端口 8080）
- 更接近生产环境配置
- 网络隔离更好

**适用场景：** 生产部署、模拟生产环境


## 推荐：使用 docker-compose.dev.yml

```bash
docker compose -f infra/compose/docker-compose.dev.yml up --build
```
