# MVP 主干重构计划

> 起草于 2026-09-02。目标：把 **AI coding agent → 回测 → 迭代** 这条 MVP 主干收敛成单一、清晰、可快速迭代的链路。
> 实盘（`risk_engine` / `trading_engine` / `live_trading_sdk`）本轮不动，另见后续计划。
>
> 本文档是迭代依据，每完成一项就更新「进度」表。

---

## 0. 一句话现状

流程是通的，但**同一件事有 3-4 套并行实现**：coding agent 有 4 条路径（其中主路径最弱），代码编辑器有 3 份拷贝，回测版本快照有 2 套写法。另有 2344 行零引用死代码。

---

## 1. 现状盘点

### 1.1 Coding Agent：4 条并行路径

| # | 入口 | 执行位置 | 机制 | 状态 |
|---|---|---|---|---|
| 1 | `POST /strategies/{id}/generate`<br>`POST /strategies/{id}/refine`（默认 mode） | Docker 容器<br>`agent.runner_v2` | `EnhancedPipeline` — **单次 LLM 吐出整个 strategy.py**，无工具调用、无迭代 | 主路径，但最弱 |
| 2 | `POST /chat/stream`（`/generate_overview`）<br>`_run_autonomous_refine()` | **API 进程内同步执行** | `AutonomousAgent` ReAct 循环 + 工具调用（`ls`/`read_file`/`search_files`/`edit_file`/`write_file`/`task_done`） | 真正的 coding agent，却只用在边角场景 |
| 3 | `POST /refine`（`mode=patch_validate` / `proposal_validate`） | **worker 进程内** | 自研 `change_spec` 引擎 + LLM 修复循环 | ~400 行塞在 job handler 里 |
| 4 | 无入口 | — | `spec_pipeline` / `pinescript_pipeline` / `plan_builder` / `BasicPipeline` | 零引用死代码 |

**关键矛盾**：能力最强的 `AutonomousAgent`（路径 2）只被用来生成 `overview.md`；产品主路径（路径 1）反而是最原始的一次性全文件生成。

**路径 3 的细节**（`services/worker/worker/main.py:1206-1620`）手写了一套 patch 格式：
- `_apply_change_spec_to_code()` — 支持 `exact_replace` / `insert_after` / `insert_before` / `range_replace` / `unified_diff` 五种操作
- `_apply_unified_diff_simple()` — 自己实现的 diff 应用
- `_repair_change_spec_with_llm()` / `_validate_refine_change_spec_with_loop()` — LLM 修复循环

而 `packages/code_editor` 里已经有一个 fuzzy 编辑器（`code_editor.core.editor.replace`），`main.py:1284` 甚至已经在用它了 —— 两套并存。

### 1.2 代码编辑器：3 份实现

```
packages/agent/agent/editor.py                    179 行  ← agent/tools.py 使用（活）
services/api/app/services/code_editor_service.py  179 行  ← 零引用，与上面逐字节相同（死）
packages/code_editor/core/editor.py               独立实现 ← worker/main.py:1284 使用（活）
```

`api` 和 `agent` 两个镜像都 `pip install` 了 `packages/code_editor`，但 API 侧实际用的是自己那份拷贝的死代码。

### 1.3 回测链路

链路本身清晰：

```
POST /backtests → Job(BACKTEST) → worker 起 backtest 容器
  → backtest.runner 从 versions/<version_id>/ 读 strategy.py + strategy_spec.yaml
  → data.{binance,okx,us_stock} 拉 K 线
  → vectorized.run_backtest
  → 写 metrics.json / trades.json / equity_curve.json / candles / positions / run_meta
  → worker 回读 metrics.json 入库
```

问题：

**(a) 版本快照两套写法，15 处创建点**

```python
# 写法 A：容器自己往 version_dir 写，路径硬编码
version.workspace_path = f"versions/{version.id}"
# 写法 B：从 strategy_dir 拷贝快照
version.workspace_path = snapshot_current_strategy_to_version(...)
```

`StrategyVersion(` 在 `backtests.py` / `strategies.py` / `strategies_import.py` 中出现 **15 次**，统一是「先 `workspace_path=""` 建对象 → 再补路径」的两步模式。任一处漏了第二步，版本就指向空目录，回测失败且难排查。

**(b) 回测「成功」但 metrics 可能为空**

`services/worker/worker/main.py:425` —— `metrics.json` 读取失败被 `except Exception: pass` 静默吞掉，`run.status` 仍置为 `SUCCEEDED`，前端拿到空指标。

**(c) 行情数据每次现拉，crypto 无缓存**

`backtest/runner.py:195` 每跑一次回测就重新请求交易所。只有美股有缓存（`data/us_stock.py:82-106` 的 `_read_cache`/`_write_cache`，parquet + meta，TTL 7 天），OKX / Binance 完全没有。

**这是 agent 迭代速度的最大瓶颈** —— agent 每改一版策略就要重拉一次全量 K 线，还容易撞限流。

**(d) 每 job 一容器，无复用、无重试、无结果缓存**

`generate_and_backtest` 一轮起 2 个容器。同一 version + 同一 dataset 重复回测会完整重跑。

**(e) agent 拿不到回测结果**

agent 生成完代码就结束，只跑 `smoke_validation` 静态检查 + 200 根 bar 的冒烟回测。**没有「看 metrics → 改进 → 再回测」的闭环**。`agent/skills.py` 里已经定义了 skill 框架但没接回测工具。

### 1.4 结构问题

**巨型文件**

| 文件 | 行数 | 问题 |
|---|---|---|
| `services/api/app/routers/strategies.py` | 2906 | 27 个 endpoint，混杂 members / exchange_accounts / signals / trades / chat / generate / refine / versions / files / git |
| `services/worker/worker/main.py` | 2534 | 13 种 job 一条 elif 链（`main.py:2045-2083`），MVP 只需 4 种 |
| `packages/backtest/backtest/artifacts.py` | 645 | — |
| `apps/web/src/components/console/DashboardHome.tsx` | 1546 | — |

**12 个包里只有 6 个在 MVP 主干上**

```
MVP 主干:  control_plane  agent  backtest  data  code_editor  okx_sdk
实盘（本轮不动）: risk_engine  live_trading_sdk
外围/停用:
  youtube_processor      Dockerfile 里已注释禁用（torch ~800MB）
  tradingview_scraper    核心抓取未实现，IMPLEMENTATION_TODO 全部未勾选
  trending_scraper       定时抓 TradingView 榜单
  strategy_templates     模板体系 —— 与 MVP 主干平行的第二套完整流程
```

`strategy_templates` 相关：`template_backtest_job.py`(819) + `template_stable5_screening_job.py`(491) + `template_performance_job.py`(151) + 4 个 `templates*.py` router，构成了与 MVP 主干并行的第二套策略/回测流程。

**依赖管理不统一**：packages 用 `pyproject.toml`，services 用 `requirements.txt`，Dockerfile 手工 `pip install` 8 个本地包，无 lock 文件。

---

## 2. 四步迭代计划

### 第一步：收敛 coding agent 为单一实现

**目标**：`AutonomousAgent` 成为唯一的 coding agent；容器化执行；删除其余三条路径。

**改动**

1. `packages/agent/agent/runner_v2.py` — 用 `AutonomousAgent` 替换 `EnhancedPipeline.run()`
   - 容器入口不变（`python -m agent.runner_v2`），worker 侧零改动
   - `workspace_root` 指向 `version_dir`（而非 `strategy_dir`），保证版本隔离
   - 保留 `EnhancedPipeline` 的 Langfuse tracing / `SessionMetrics`，接到 `AutonomousAgent` 上
   - 保留 `LLM_FALLBACK_ON_ERROR` 的 fallback 策略行为

2. 删除路径 3 的自研 patch 引擎（`worker/main.py:1206-1620`，约 400 行）
   - `_apply_change_spec_to_code` / `_apply_unified_diff_simple` / `_repair_change_spec_with_llm` / `_validate_refine_change_spec_with_loop` / `_normalize_refine_json` / `_parse_json_change_spec`
   - `mode=patch_validate` / `proposal_validate` 两个分支随之下线（先确认前端 `CodeView.tsx` 是否还在调）

3. 代码编辑器三份合一
   - 删 `services/api/app/services/code_editor_service.py`（零引用死代码）
   - `packages/agent/agent/editor.py` → 改为 `from code_editor.core.editor import ...` 的薄封装，或直接让 `agent/tools.py` 用 `code_editor`
   - 最终只保留 `packages/code_editor` 一份实现

4. 删除死代码（清单见 §3）

**验收标准**
- `POST /generate` 和 `POST /refine` 都走 `AutonomousAgent` 容器，产物落在 `versions/<id>/`
- `agent.log` 里能看到工具调用序列（read → edit → verify）
- 现有 `services/api/tests/test_integration_workflow.py` 的 E2E 通过

---

### 第二步：agent 闭环接上回测反馈

**目标**：agent 能在生成后自己跑回测、读 metrics、判断好坏、迭代改进。这是 MVP 的核心价值点。

**改动**

1. 给 `agent/skills.py` 加 `backtest` skill
   - 输入：symbol / interval / 时间范围（从策略 spec 或默认预设取）
   - 执行：直接在 agent 容器内调 `backtest.runner` 的核心函数（agent 镜像已经 `COPY packages/backtest` 和 `packages/data`，不需要另起容器）
   - 输出：`metrics.json` 的关键字段（total_return / sharpe / max_drawdown / win_rate / total_trades）+ 失败时的错误摘要

2. `AutonomousAgent` 的 system prompt 加入迭代约定
   - 生成代码 → 调 `backtest` skill → 看指标 → 不满意就改 → 再回测
   - 加迭代上限（`AgentConfig` 已有 `max_steps` / token budget）
   - 加终止条件：指标达标 或 达到迭代上限 或 连续 N 次无改善

3. 每轮迭代的 metrics 记录进 `agent.log` 和 `StrategyVersion.llm_meta`，前端可展示「agent 迭代了 3 轮，sharpe 从 0.4 → 1.1」

4. 复用现有 `smoke_validation` 作为回测前的静态门禁（语法 + 协议格式检查），避免把明显错的代码送去跑全量回测

**依赖**：第三步的缓存层。没有缓存，agent 每轮迭代都重拉 K 线，这一步会慢到不可用。**建议第二、三步一起做，或第三步先行。**

**验收标准**
- 一次 `POST /generate` 能看到 agent 自主跑了 ≥2 轮回测
- `agent.log` 里有每轮的 metrics
- 端到端耗时可接受（缓存命中时单轮回测 < 5s）

---

### 第三步：K 线缓存层

**目标**：消除 agent 迭代循环里的重复取数，这是迭代体感提升最直接的一项。

**改动**

1. `packages/data` 新增 `cache.py`，把 `us_stock.py:82-106` 已有的 parquet + meta 缓存模式抽成通用层
   - key：`{exchange}_{symbol}_{interval}` + 时间范围
   - 存储：parquet（已有 pandas 依赖），落在 workspaces volume 上（容器间共享）
   - 支持增量：已缓存 `[t0, t1]`，请求 `[t0, t2]` 时只拉 `[t1, t2]` 追加
   - 历史 K 线不变，TTL 只对「最近 N 根」生效

2. `data/okx.py` 的 `fetch_candles()` 和 `data/binance.py` 的 `fetch_klines()` 接入缓存层
3. `data/us_stock.py` 迁移到统一缓存层，去掉自己那份实现
4. 环境变量统一：现有的 `US_STOCK_CACHE_DIR` / `US_STOCK_CACHE_TTL_DAYS` → `MARKET_DATA_CACHE_DIR` / `MARKET_DATA_CACHE_TTL_*`（保留旧变量做兼容）
5. 缓存目录挂进 agent 镜像和 backtest 镜像（两者都用 `workspaces` volume，加个子目录即可）

**注意**：`backtest/network_guard.py` 的 allowlist 机制不受影响，缓存命中时根本不发网络请求。

**验收标准**
- 同一 dataset 第二次回测不产生任何交易所请求
- 单轮回测（缓存命中）耗时 < 5s

---

### 第四步：结构拆分

**目标**：让 MVP 主干在代码结构上可见。

**改动**

1. **拆 `routers/strategies.py`（2906 行 / 27 endpoint）**

   ```
   strategies_crud.py       创建/列表/详情/live-ready
   strategies_chat.py       chat / chat/stream / chat/confirm
   strategies_generate.py   generate / refine / live/generate / live/confirm
   strategies_versions.py   versions / restore / files / workspace compare / git compare
   strategy_members.py      members CRUD
   strategy_accounts.py     exchange_accounts CRUD + signals + trades
   ```

2. **拆 `worker/main.py`（2534 行 / 13 种 job）**

   ```
   worker/handlers/backtest.py
   worker/handlers/generate.py       generate_strategy + generate_and_backtest
   worker/handlers/refine.py
   worker/handlers/sandbox.py
   worker/handlers/repo.py
   worker/handlers/trending.py
   worker/handlers/template.py
   worker/dispatch.py                {JobType: handler} 表，替换 elif 链
   worker/container.py               _run_container_and_stream_logs 等共用工具
   ```

3. **统一版本创建**

   `packages/control_plane` 新增工厂函数，替换 15 处散落的 `StrategyVersion(...)` + 两步赋值：

   ```python
   def create_strategy_version(
       db, *, strategy_id: str, prompt: str,
       llm_meta: dict | None = None,
       snapshot: bool = True,          # True=从 strategy_dir 拷贝, False=容器自己写
   ) -> StrategyVersion:
       ...
   ```

4. **修 metrics 静默失败**（`worker/main.py:425`）

   `metrics.json` 缺失或解析失败时，`run.status` 应置 `FAILED` 并写 `error_message`，不能报「成功」。

5. **标记/隔离外围模块**

   - `youtube_processor`：Dockerfile 已禁用 → 直接删包，或移到 `packages/_archived/`
   - `tradingview_scraper`：核心未实现 → 决定「补完」还是「删」（`pinescript_pipeline.py` 是它的下游，已在死代码清单里）
   - `trending_scraper` / `strategy_templates`：保留但在 README / CLAUDE.md 里明确标注为「非 MVP 主干」

6. **依赖管理统一**

   `services/api` 和 `services/worker` 也用 `pyproject.toml`，本地包用 path 依赖，Dockerfile 里的 8 条手工 `pip install` 收敛成一条。

7. **更新 `CLAUDE.md`**（当前已严重脱节）

   - `packages/strategy_sdk/` → 实际是 `live_trading_sdk/`
   - `enhanced_executor.py` / `enhanced_monitor.py` / `enhanced_manager.py` 已不存在（已合并回 `executor.py` / `monitor.py` / `manager.py`）
   - 补充未提及的 `code_editor` / `strategy_templates` / `trending_scraper` / `youtube_processor`

**验收标准**
- 单文件 < 800 行
- `worker/dispatch.py` 一眼看出 13 种 job 分别归谁
- CLAUDE.md 里提到的每个路径都真实存在

---

## 3. 死代码删除清单

以下模块经**反向依赖扫描 + 裸名 grep（含字符串/动态引用/Dockerfile/compose/前端）双重确认**，零引用。

判据不只是"零引用"，还逐个核对过 §4.5 那条修正后的标准 —— **有没有恢复意图**：
这批文件中没有一个带 `temporarily disabled` / `TODO` / `WIP` 标记，也没有任何
（哪怕被注释掉的）调用点。与 `youtube_processor` 的区别见 §4.5。已确认删除。
需要时都可从 git 历史取回。

| 文件 | 行数 | 说明 |
|---|---|---|
| `packages/agent/agent/pinescript_pipeline.py` | 519 | PineScript→Python 转换的**另一套实现**（preprocess → IR → codegen → 验证/修复循环），从未接线。线上转换走的是 `strategies_import._build_pinescript_conversion_prompt` + `GENERATE_STRATEGY` job，功能不受影响 |
| `packages/agent/agent/prompt/indicator_tools.py` | 488 | 指标工具定义，`prompt/__init__.py` 都没导出 |
| `packages/agent/agent/spec_pipeline.py` | 389 | spec-loop 生成流水线，无调用点 |
| `packages/agent/agent/plan_builder.py` | 287 | `PlanBuilder` 全仓零引用 |
| `packages/agent/agent/pipeline/basic.py` | 189 | `BasicPipeline` 仅被自己的 `__init__` 引用 |
| `services/api/app/services/code_editor_service.py` | 179 | 与 `agent/editor.py` 逐字节相同，零引用 |
| `packages/agent/agent/test_imports.py` | 170 | 导入冒烟脚本（非 pytest），引用了将被删的 `BasicPipeline` |
| `packages/agent/agent/network_guard.py` | 123 | 全仓都在用 `backtest.network_guard`，这份没人用 |
| **合计** | **2344** | |

连带修改：`packages/agent/agent/pipeline/__init__.py` 移除 `BasicPipeline` 的 import 和 `__all__` 条目。

### 已确认**不是**死代码（勿删）

| 模块 | 使用者 |
|---|---|
| `agent/skills.py` | `AutonomousAgent.__init__` / `_run_skill_tool` / `_get_tool_definitions` |
| `agent/context_manager.py` | `AutonomousAgent` 的上下文压缩 |
| `agent/editor.py` | `agent/tools.py:10` 的 `CodeEditor` |
| `agent/observability/*` | `runner_v2` / `pipeline/enhanced` |
| `agent/middleware/` | `runner_v2` / `smoke_validation` |
| `agent/prompt/indicator_docs.py` | `prompt/context.py` |
| `agent/templates.py` | `runner_v2`（fallback 策略 + 默认 spec） |

---

## 4. 目标架构

```
用户 prompt
   ↓
POST /strategies/{id}/generate  (API，只建 Job)
   ↓
Job(GENERATE_STRATEGY) → Redis
   ↓
worker/dispatch.py → handlers/generate.py
   ↓
Docker 容器: agent.runner_v2
   └─ AutonomousAgent (唯一 coding agent)
        ├─ tools: ls / read_file / search_files / edit_file / write_file
        ├─ skill: backtest  ←──┐
        │                      │  闭环迭代
        │   写 strategy.py     │
        │   → 跑回测           │
        │   → 读 metrics ──────┘
        │   → 不满意就改
        └─ task_done
   ↓
versions/<version_id>/{strategy.py, strategy_spec.yaml, agent.log, ...}
   ↓
POST /backtests → Job(BACKTEST) → Docker 容器: backtest.runner
   └─ data.* → 缓存层 (parquet, workspaces volume) → 交易所
   ↓
runs/<run_id>/{metrics.json, trades.json, equity_curve.json, ...}
```

**单一职责**：
- `packages/code_editor` — 唯一的代码编辑实现
- `packages/agent/AutonomousAgent` — 唯一的 coding agent
- `packages/data/cache.py` — 唯一的取数入口
- `control_plane.create_strategy_version()` — 唯一的版本创建入口

---

## 5. 进度

| 步骤 | 状态 | 备注 |
|---|---|---|
| 0. 删除死代码（2344 行） | ✅ 2026-09-02 | 8 个文件；残留引用扫描 + compileall 通过 |
| 1. 收敛 coding agent | ✅ 2026-09-02 | `runner_v2` 改用 `AutonomousAgent`；worker 自研 patch 引擎删除 527 行；editor 三份合一 |
| 2. agent 闭环接回测 | ✅ 2026-09-02 | `agent/backtest_tool.py` + 重新启用 `BacktestSkill`（真实数据 + 运行预算） |
| 3. K 线缓存层 | ✅ 2026-09-02 | `data/cache.py` + 三个 provider 接入；env 透传进 agent/backtest 容器 |
| 4.1 拆 strategies.py | ✅ 2026-09-02 | 拆出 members / accounts / workspace 三个 router；2906 → 2394 行 |
| 4.2 拆 worker/main.py | ✅ 2026-09-02 | elif 链 → `JOB_HANDLERS` 表；13 种 JobType 机器校验全覆盖 |
| 4.3 统一版本创建 | ✅ 2026-09-02 | `control_plane/versions.py`；MVP 路径 11 处全部改用工厂 |
| 4.4 修 metrics 静默失败 | ✅ 2026-09-02 | metrics 缺失/损坏/为空 → `FAILED` + error_message |
| 4.5 隔离外围模块 | ✅ 2026-09-02 | 三个外围模块全部保留并标注；无删除 |
| 4.6 依赖管理统一 | ✅ 2026-09-02 | 11 个包 + 2 个服务全部 pyproject.toml；4 个镜像实际构建并运行验证 |
| 4.7 更新 CLAUDE.md | ✅ 2026-09-02 | 修正过时引用 + 新增 agent/缓存/版本/dispatch/测试章节 |

### 4.5 的处理结果

**结论：一个都没删，只做标注。**

| 模块 | 处理 | 依据 |
|---|---|---|
| `youtube_processor` | **保留为「暂时禁用」状态** | 见下方说明 |
| `tradingview_scraper` | 保留 | 原判断有误：它已装进 API 镜像且 `get_pinescript` 正被导入端点使用。`IMPLEMENTATION_TODO.md` 针对的是更难的一类 URL，不是"整体未实现"。只有它的下游 `pinescript_pipeline.py` 是死代码（步骤 0 已删） |
| `trending_scraper` / `strategy_templates` | 保留 + 标注 | 功能在用；已在 CLAUDE.md 仓库结构里按 MVP 主干 / 实盘 / 外围三段分区 |

#### 关于 youtube_processor：为什么不能按"不可达"删

这个模块一度被本轮删除，随后恢复。记录这个判断错误，避免重犯：

当时的删除依据是端到端不可达 —— 镜像里没装、端点必返回
`youtube_processor_not_installed`、前端 tab 被注释掉点不到。事实无误，但**判据用错了**：

> 三处注释写的都是 **"temporarily disabled"**，不是 deprecated/removed。
> 对一个被临时停用的功能来说，"不可达"恰恰是停用的**预期状态**——
> 这个判据根本区分不出"已死"和"暂时停在这里"。

而且停用原因是外部且会变的：镜像体积（`torch ~800MB` + `whisper ~200MB` +
`torchaudio ~200MB`）和 YouTube 的抓取限制，都不是"设计不对要重做"。
它也不是几行胶水：`downloader.py` 242 行 + `transcriber.py` 171 行 +
`prompt_builder.py` 140 行是能跑的下载/转录/提示词逻辑。

**判据修正**：删除的依据应当是"没有恢复意图"，而不是"当前不可达"。
注释里写 temporarily / TODO / disabled 的，一律按 parked 处理，保留并标注。

恢复后它仍是原来的禁用状态（Dockerfile 注释、前端 tab 注释、compose env 保留），
唯一的改动是端点也改用了 `create_strategy_version` 工厂，与 TradingView 导入一致。

### 4.6 的处理结果

- 补齐 `agent` / `backtest` / `control_plane` / `data` 四个包的 `pyproject.toml`
  （此前无任何打包文件，只靠 `COPY` 源码目录）；`risk_engine` 的 `setup.py` 转为 `pyproject.toml`。
  现在 11 个包全部统一。
- 新增 `services/api/pyproject.toml`（测试依赖放 `test` extra）和
  `services/worker/pyproject.toml`，删除两个 `requirements.txt`，Dockerfile 改为从 pyproject 安装。
- **本地包一律不写进 `dependencies`**：`data` / `agent` / `backtest` 这些名字在 PyPI 上
  都指向无关项目，写进去会装错包。已在 pyproject 注释和 CLAUDE.md 里写明。
- 同步修正 `AGENTS.md` 和 `services/api/tests/README.md` 里失效的 `pip install -r requirements.txt`。

### 验证方式

| 项 | 结果 |
|---|---|
| 包测试（本机） | **135 passed, 4 failed**（4 个为既有失败，已在原始代码上复现确认） |
| 包测试（真实镜像内） | agent 镜像 **56 passed**；backtest 镜像 cache 测试 **19 passed**（真实 parquet） |
| 镜像构建 | api / worker / agent / backtest **四个全部构建成功** |
| 镜像运行 | 四个镜像均实际 `docker run` 验证：API 加载出 139 条路由、worker `JOB_HANDLERS` 13/13、agent skills 含 `backtest`、缓存目录共享一致 |
| API 路由表 | 拆分后 140 条零差异；删 youtube 后 **139 = 140 − 1**，差异仅该端点 |
| 前端 | `npm run build` 成功；tsc 错误 107 → 103，**我引入 0**，顺带消掉 4 个 |
| ruff (F401/F821/F811) | 112 → 65，**我引入 0** |

### 顺带修掉的既有 bug

1. **`tools.run_backtest` 的 `NameError`** —— `np` 在嵌套 `import numpy as np` 之前就被使用，
   而模块顶部并未导入 numpy，导致合成数据路径必然抛 `name 'np' is not defined`
   （被外层 `except` 吞掉，表现为 "System Error"）。ruff 的 `F821` ×3 独立佐证。
2. **`test_enhanced_agent.py` 从未能被收集** —— 引用了已不存在的 `LoopDetector` /
   `SubAgentType` / `SUBAGENT_CONFIGS` / `HelpSkill`。已裁剪到与现有 API 一致，现 14 个用例可跑。
3. **`strategy_workspace.py` 的 `Strategy` 未导入** —— 我拆分时漏带，5 处函数体内引用。
   模块导入不会触发，是 ruff `F821` 抓到的；已修复。
4. **worker 镜像里 `code_editor` 根本无法导入** —— Dockerfile 是
   `COPY packages/code_editor /app/code_editor`，把项目根目录拷了进去，实际包在
   `code_editor/code_editor/`，因此 `import code_editor.core` 必然
   `ModuleNotFoundError`。原 `worker/main.py:1284` 的 `from code_editor.core.editor import replace`
   在生产里只要走到 `exact_replace` 分支就会炸（在函数内，导入期发现不了）。
   已改为与 API 镜像一致的 `pip install`，并在镜像内验证通过。

## 6. 需要决策的问题

1. **`tradingview_scraper` 去留** —— 核心抓取（PineScript 源码）未实现，`IMPLEMENTATION_TODO.md` 全部未勾选，下游 `pinescript_pipeline.py` 已在删除清单。补完需要引 Playwright + 在镜像里装 chromium。是补完还是砍掉？

2. **`strategy_templates` 定位** —— 它是与 MVP 主干平行的第二套策略/回测流程（约 1500+ 行 worker job + 4 个 router）。是 MVP 的一部分，还是可以先冻结？

3. **`mode=patch_validate` / `proposal_validate` 是否还在用** —— 删除路径 3 前需确认前端 `CodeView.tsx` / `ImportStrategyModal.tsx` 是否还在调这两个模式。

4. **agent 迭代预算** —— 闭环迭代的上限设多少轮？每轮回测的默认 dataset（symbol/interval/时间范围）用什么？这直接影响成本和耗时。
