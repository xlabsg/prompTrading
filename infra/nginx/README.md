# Nginx 部署指南 - PromptTrading Platform

## 部署架构

Nginx 部署在**宿主机**上，作为反向代理。

**为什么选择宿主机部署：**
- ✅ SSL 证书管理简单（Let's Encrypt/Certbot 自动续期）
- ✅ 行业标准做法，成熟稳定
- ✅ 性能最优（减少一层容器网络）
- ✅ 调试和监控工具齐全
- ✅ 可以同时代理多个应用

```
Internet
    ↓
[Nginx (宿主机:80/443)]
    ↓
    ├─→ [Frontend Container:3000] (React SPA)
    ├─→ [API Container:8000]      (FastAPI)
    └─→ [WebSocket:8000/ws]       (Real-time)
```

## 部署步骤

### 1. 安装 Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx

# 验证安装
nginx -v
```

### 2. 安装 Certbot (Let's Encrypt)

```bash
# Ubuntu/Debian
sudo apt install certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install certbot python3-certbot-nginx

# 验证安装
certbot --version
```

### 3. 配置 Nginx

```bash
# 复制配置文件
cd /path/to/prompTrading
sudo cp infra/nginx/prompt-trading.conf /etc/nginx/sites-available/

# 创建软链接
sudo ln -s /etc/nginx/sites-available/prompt-trading.conf /etc/nginx/sites-enabled/

# 创建 certbot webroot 目录
sudo mkdir -p /var/www/certbot

# 测试配置（此时会因为没有SSL证书而失败，正常）
sudo nginx -t
```

### 4. 临时移除 SSL 配置获取证书

由于还没有 SSL 证书，需要先注释掉 SSL 相关配置：

```bash
sudo nano /etc/nginx/sites-available/prompt-trading.conf
```

**临时修改**：注释掉 HTTPS server block（line 31-185），只保留 HTTP server block (line 11-24)

### 5. 获取 SSL 证书

```bash
# 确保 DNS 已经指向服务器 IP
dig ai.example.com

# 获取证书（使用 webroot 模式）
sudo certbot certonly --webroot \
  -w /var/www/certbot \
  -d ai.example.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# 或使用 nginx 插件（自动配置）
sudo certbot --nginx -d ai.example.com
```

### 6. 恢复完整 Nginx 配置并启用 OCSP Stapling

```bash
# 编辑配置文件
sudo nano /etc/nginx/sites-available/prompt-trading.conf

# 取消 OCSP stapling 相关行的注释（约 line 48-52）
# ssl_stapling on;
# ssl_stapling_verify on;
# resolver 8.8.8.8 8.8.4.4 valid=300s;
# resolver_timeout 5s;

# 测试配置
sudo nginx -t

# 重新加载 Nginx
sudo systemctl reload nginx
```

**注意**：
- OCSP Stapling 仅在使用 Let's Encrypt 等正规 CA 证书时启用
- 自签名证书不支持 OCSP，保持注释状态即可

### 7. 设置证书自动续期

```bash
# Certbot 会自动添加续期 cron job，验证：
sudo systemctl status certbot.timer

# 或手动添加到 crontab
sudo crontab -e
# 添加以下行：
# 0 0,12 * * * /usr/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"

# 测试续期（dry run）
sudo certbot renew --dry-run
```

### 8. 启动 Docker 服务

```bash
cd infra/compose

# 开发环境
docker compose -f docker-compose.dev.yml up -d

# 生产环境
docker compose -f docker-compose.yml up -d

# 验证服务运行
docker compose ps
curl http://localhost:3000  # Frontend
curl http://localhost:8000/health  # API
```

### 9. 验证部署

```bash
# 测试 nginx 配置（应该没有警告）
sudo nginx -t

# 检查 nginx 错误日志（确认没有警告）
sudo tail -20 /var/log/nginx/error.log

# 检查 HTTPS
curl -I https://ai.example.com

# 检查 SSL 评分（推荐）
# https://www.ssllabs.com/ssltest/analyze.html?d=ai.example.com

# 检查 WebSocket 连接
wscat -c wss://ai.example.com/ws
```

## 防火墙配置

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 'Nginx Full'
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 日志管理

```bash
# 实时查看访问日志
sudo tail -f /var/log/nginx/prompt-trading-access.log

# 实时查看错误日志
sudo tail -f /var/log/nginx/prompt-trading-error.log

# 日志轮转（nginx 默认已配置）
cat /etc/logrotate.d/nginx
```

## 性能优化

### Worker Processes

```nginx
# /etc/nginx/nginx.conf
worker_processes auto;  # 自动根据 CPU 核心数设置
worker_connections 4096;  # 每个 worker 的连接数
```

### 缓存配置（可选）

```nginx
# 在 http block 中添加
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m use_temp_path=off;

# 在 location /api 中添加
proxy_cache api_cache;
proxy_cache_valid 200 5m;
proxy_cache_key "$scheme$request_method$host$request_uri";
add_header X-Cache-Status $upstream_cache_status;
```

## 监控

### 启用 Nginx Status

```nginx
# 在 server block 中添加
location /nginx_status {
    stub_status on;
    access_log off;
    allow 127.0.0.1;
    deny all;
}
```

### 查看状态

```bash
curl http://localhost/nginx_status
```

## 故障排查

### 常见问题

1. **Nginx 警告: "listen ... http2" is deprecated**
   - 原因：Nginx 1.25.1+ 版本语法变更
   - 解决：配置文件已更新为新语法 (`http2 on;`)
   - 验证：`sudo nginx -t` 应该没有警告

2. **Nginx 警告: "ssl_stapling" ignored**
   - 原因：使用自签名证书或证书不支持 OCSP
   - 解决：配置文件已默认注释 OCSP stapling
   - 使用 Let's Encrypt 后取消注释即可启用

3. **502 Bad Gateway**
   - 检查后端容器是否运行：`docker compose ps`
   - 检查端口是否正确：`netstat -tlnp | grep -E '3000|8000'`
   - 查看 nginx 错误日志

4. **SSL 证书错误**
   - 检查证书路径：`ls -la /etc/letsencrypt/live/ai.example.com/`
   - 测试证书：`sudo certbot certificates`
   - 强制续期：`sudo certbot renew --force-renewal`

5. **WebSocket 连接失败**
   - 确认 Upgrade 和 Connection 头配置正确
   - 检查超时设置（WebSocket 需要长连接）
   - 查看浏览器开发者工具 Network 标签

6. **权限问题**
   - Nginx 日志权限：`sudo chown -R www-data:www-data /var/log/nginx/`
   - Certbot webroot：`sudo chown -R www-data:www-data /var/www/certbot/`

### 调试命令

```bash
# 检查 nginx 配置语法
sudo nginx -t

# 查看 nginx 主进程和 worker 进程
ps aux | grep nginx

# 检查端口占用
sudo netstat -tlnp | grep nginx

# 测试 DNS 解析
nslookup ai.example.com

# 测试 SSL 握手
openssl s_client -connect ai.example.com:443

# 重启 nginx
sudo systemctl restart nginx
```

## 更新环境变量

别忘了更新 Docker Compose 的环境变量：

```bash
# infra/compose/.env
APP_PUBLIC_BASE_URL=https://ai.example.com
APP_GITHUB_OAUTH_REDIRECT_URI=https://ai.example.com/auth/github/callback
```

然后重启容器：

```bash
cd infra/compose
docker compose down
docker compose up -d
```


## 安全检查清单

- [ ] SSL 证书有效且自动续期
- [ ] HTTP 强制重定向到 HTTPS
- [ ] HSTS 头已启用
- [ ] 安全响应头已配置（X-Frame-Options, CSP 等）
- [ ] 隐藏文件访问被拒绝
- [ ] 防火墙规则已配置
- [ ] 日志轮转已启用
- [ ] 定期更新 nginx 和系统补丁

## 参考资源

- [Nginx 官方文档](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [SSL Labs Server Test](https://www.ssllabs.com/ssltest/)
