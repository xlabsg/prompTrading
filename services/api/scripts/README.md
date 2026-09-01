# Trending & Templates 初始化脚本使用指南

本目录包含用于初始化和维护 Trending 和 Templates 数据的脚本。

## 🚀 快速开始

### 一键初始化（推荐）

```bash
cd services/api

# 运行一键初始化脚本
./scripts/init_trending_templates.sh
```

这将：
1. ✅ 初始化 5 个内置策略模板
2. ✅ 配置 Trending 定时抓取任务
3. ✅ 配置 Templates 性能更新任务
4. 🔄 可选：触发 Trending 抓取
5. 🔄 可选：生成 Templates 性能数据

## 📁 可用脚本

### 初始化脚本

| 脚本 | 说明 |
|------|------|
| `init_trending_templates.sh` | 一键初始化所有数据 |
| `seed_builtin_templates.py` | 初始化内置策略模板 |
| `setup_trending_schedule.py` | 配置 Trending 定时任务 |
| `setup_template_performance_schedule.py` | 配置 Templates 性能更新任务 |

### 数据生成脚本

| 脚本 | 说明 |
|------|------|
| `trigger_trending_scrape.py` | 手动触发 TradingView 抓取 |
| `generate_template_performance.py` | 生成模板性能数据 |
| `verify_trending_templates.py` | 验证数据是否正确 |

## 📖 详细使用说明

### 1. 初始化内置模板

```bash
cd services/api
python scripts/seed_builtin_templates.py
```

**输出示例：**
```
📝 开始初始化内置模板...
✅ 模板初始化完成！
   - 总模板数: 5
   - 精选模板: 4

📊 已初始化的模板:
   ⭐ - Moving Average Crossover
      类型: builtin, 质量: 85.0, 风险: low, 频率: low_frequency
   ⭐ - RSI Mean Reversion
      类型: builtin, 质量: 82.0, 风险: medium, 频率: medium_frequency
   ...
```

### 2. 配置定时任务

#### Trending 定时抓取

```bash
python scripts/setup_trending_schedule.py
```

**默认配置：**
- 每 6 小时抓取一次
- 每次最多 50 个策略
- 最低质量分 30
- 自动回测前 15 个

#### Templates 性能更新

```bash
python scripts/setup_template_performance_schedule.py
```

**默认配置：**
- 每天凌晨 2 点 UTC 更新
- 每批处理 5 个模板
- 生成 90 天历史数据
- 每天生成 3 个信号

### 3. 触发 Trending 抓取

```bash
# 基础用法
python scripts/trigger_trending_scrape.py

# 自定义参数
python scripts/trigger_trending_scrape.py \
  --max-count 100 \
  --min-quality 40.0 \
  --backtest-top-n 20

# 只抓取不回测
python scripts/trigger_trending_scrape.py --no-backtest
```

**参数说明：**
- `--max-count`: 最大抓取数量（默认 50）
- `--min-quality`: 最低质量分数（默认 30.0）
- `--backtest-top-n`: 回测前 N 个（默认 10）
- `--no-backtest`: 不自动回测

**输出示例：**
```
🔄 触发 Trending 抓取任务...
✅ Trending 抓取任务已创建: a1b2c3d4...

任务配置:
   - 最大抓取: 50
   - 最低质量: 30.0
   - 自动回测: True
   - 回测数量: 10

等待 Worker 处理...
查看日志: docker compose logs -f worker
```

### 4. 生成模板性能数据

```bash
python scripts/generate_template_performance.py
```

**输出示例：**
```
📊 开始生成模板性能数据...
找到 5 个公开模板

[1/5] 处理: Moving Average Crossover
  ✅ 完成
[2/5] 处理: RSI Mean Reversion
  ✅ 完成
...

✅ 所有模板性能数据生成完成！
```

### 5. 验证数据

```bash
python scripts/verify_trending_templates.py
```

**输出示例：**
```
🔍 Trending & Templates 数据验证

============================================================
  📚 Templates 数据检查
============================================================

总模板数: 5
公开模板: 5
精选模板: 4
内置模板: 5
总订阅数: 0

模板列表:
  ⭐ Moving Average Crossover
     类型: builtin, 质量: 85.0, 风险: low, 订阅: 0
  ...

============================================================
  📈 Trending 数据检查
============================================================

总策略数: 50
回测完成: 10
等待回测: 40
回测失败: 0
平均质量: 45.2

Top 5 策略:
  BTC Momentum Strategy...
     质量: 78.5, 状态: completed, 点赞: 1234
  ...

============================================================
  ⏰ 定时任务配置检查
============================================================

Trending 定时任务:
  状态: ✅ 启用
  Cron: 0 */6 * * *
  抓取数: 50
  质量阈值: 30.0
  自动回测: True

Templates 性能更新:
  状态: ✅ 启用
  Cron: 0 2 * * *
  每批处理: 5
  历史天数: 90
```

## 🔧 生产环境部署

### 首次部署

```bash
# 1. 进入 API 目录
cd services/api

# 2. 设置环境变量
export APP_DB_URL="postgresql+psycopg://user:pass@host:5432/db"
export APP_REDIS_URL="redis://host:6379/0"

# 3. 运行一键初始化（选择不立即抓取）
./scripts/init_trending_templates.sh

# 4. 验证数据
python scripts/verify_trending_templates.py
```

### 定期维护

#### 检查定时任务状态

```bash
# 查看最近一次运行时间
psql $DATABASE_URL -c "
SELECT
    'Trending' as name,
    last_run_at,
    enabled
FROM trending_schedules
UNION ALL
SELECT
    'Templates' as name,
    last_run_at,
    enabled
FROM template_performance_schedules;
"
```

#### 手动触发数据更新

```bash
# 更新 Trending（如需要）
python scripts/trigger_trending_scrape.py --max-count 50

# 更新 Templates 性能（通常由定时任务自动完成）
python scripts/generate_template_performance.py
```

#### 监控数据质量

```bash
# 检查 Trending 数据质量
psql $DATABASE_URL -c "
SELECT
    COUNT(*) as total,
    AVG(quality_score) as avg_quality,
    COUNT(*) FILTER (WHERE quality_score >= 50) as high_quality,
    COUNT(*) FILTER (WHERE backtest_status = 'completed') as completed
FROM tradingview_trending_strategies;
"

# 检查 Templates 订阅情况
psql $DATABASE_URL -c "
SELECT
    COUNT(*) as total_templates,
    SUM(subscriber_count) as total_subscriptions,
    AVG(subscriber_count) as avg_subs
FROM strategy_templates
WHERE is_public = true;
"
```

## 🐛 故障排查

### 问题 1: 模板未显示

**检查：**
```bash
# 验证数据库中是否有数据
python scripts/verify_trending_templates.py

# 检查 API 是否正常
curl http://localhost:8000/templates | jq '. | length'
```

**解决：**
```bash
# 重新初始化模板
python scripts/seed_builtin_templates.py
```

### 问题 2: Trending 抓取失败

**检查：**
```bash
# 查看 Worker 日志
docker compose logs -f worker | grep -i trending

# 检查环境变量
echo $LLM_API_KEY
echo $OPENAI_API_KEY
```

**可能原因：**
- LLM API key 未配置（PineScript 转换需要）
- Worker 服务未运行
- Docker 镜像未构建

**解决：**
```bash
# 配置 API key
export LLM_API_KEY="your-api-key"

# 重启 Worker
docker compose restart worker

# 检查镜像
docker images | grep stratsmith
```

### 问题 3: 定时任务不执行

**检查：**
```bash
# 查看配置
python scripts/verify_trending_templates.py

# 查看 Worker 日志
docker compose logs worker | grep -i scheduler
```

**可能原因：**
- Scheduler 未启用
- Cron 表达式错误
- Worker 服务重启

**解决：**
```bash
# 重新配置
python scripts/setup_trending_schedule.py
python scripts/setup_template_performance_schedule.py

# 重启 Worker
docker compose restart worker
```

### 问题 4: 性能数据为空

**检查：**
```bash
# 查看是否有历史数据
psql $DATABASE_URL -c "
SELECT COUNT(*) FROM template_performance_runs;
SELECT COUNT(*) FROM template_signals;
"
```

**解决：**
```bash
# 手动生成
python scripts/generate_template_performance.py
```

## 📊 数据统计

### 查看整体统计

```bash
python scripts/verify_trending_templates.py
```

### API 端点

```bash
# Templates
curl http://localhost:8000/templates | jq '. | length'
curl http://localhost:8000/templates/featured | jq 'length'

# Trending
curl http://localhost:8000/api/trending/stats | jq

# 订阅情况
curl http://localhost:8000/subscriptions -H "Cookie: asp_session=YOUR_TOKEN" | jq '. | length'
```

## 🔄 更新流程

### 更新内置模板

如果需要添加新的内置模板：

1. 编辑 `packages/control_plane/migrations/seed_templates.sql`
2. 运行 `python scripts/seed_builtin_templates.py`
3. 运行 `python scripts/generate_template_performance.py`

### 调整定时任务频率

```python
# 编辑脚本默认配置
vim scripts/setup_trending_schedule.py
vim scripts/setup_template_performance_schedule.py

# 重新运行
python scripts/setup_trending_schedule.py
python scripts/setup_template_performance_schedule.py

# 重启 Worker 使配置生效
docker compose restart worker
```

## 📚 相关文档

- [数据库模型](../../../packages/control_plane/control_plane/models.py)
- [API 文档](../app/routers/trending.py)
- [Worker 实现](../../../services/worker/worker/main.py)

## 💡 提示

1. **首次部署时**，建议先运行 `init_trending_templates.sh`，选择不立即抓取 Trending
2. **Trending 抓取比较耗时**（10-20 分钟），建议在低峰期手动触发
3. **定时任务会自动运行**，不需要手动干预
4. **定期验证数据**，确保数据质量
5. **监控 Worker 日志**，及时发现和解决问题
