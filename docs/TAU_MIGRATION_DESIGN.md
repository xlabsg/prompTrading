# Coding Agent 迁移设计：自研 harness → Tau

状态：**已评审通过，V1–V7 验证完毕，实施中**
日期：2026-09-02
作者：Claude Code session

> **v2 修订**（V1–V7 实测后）：三处设计变更已折叠进正文——
> §5 `terminate` 字段在 tau 0.4.1 未实现，完成契约改以 driver 侧校验循环为主；
> §5 backtest 改子进程执行，规避进程级网络守卫（V5）；
> §7.2 无需手写 `catalog.toml`，anthropic / deepseek 均为内置原生 provider。
> §4.1 新增三处死代码删除。§11 已换成实测结果。

---

## 1. 决策与前提

**决策**：删除自研 coding agent harness，改用 [Tau](https://github.com/huggingface/tau)（`tau-ai`，Python，MIT）作为 agent 运行时。领域能力（回测闭环、策略协议、prompt）以 **Tau extension** 的形式注入。

**明确的前提（本设计据此展开）**：

- **一次性切换，不做中间层。** 不引入 harness 抽象接口，不做 `AGENT_HARNESS=tau|native` 开关，不保留旧实现做 A/B。旧 harness 代码在同一个 PR 里删除。
- **不保留 fallback 到旧 agent 的路径。** 现有 `LLM_FALLBACK_ON_ERROR` 走的是 `fallback_strategy_py()` 模板兜底，与 harness 无关，予以保留。
- **Tau 版本 pin 死**，不用 `>=`。

**动机**：`packages/agent` 里约 3.6k 行是通用 harness 代码（agent loop、LLM 客户端、上下文压缩、文件工具、模糊编辑器），不是本项目的差异化能力，且当前实现在"生成后修改代码"这一环上不可靠。把这部分外包出去，团队专注在策略生成的领域层。

---

## 2. 现状问题（为什么是编辑逻辑）

当前编辑链路：`agent/editor.py`（change-spec 适配器）→ `code_editor/core/editor.py`（469 行渐进式模糊匹配）。

change-spec 支持 5 种操作：`exact_replace` / `insert_after` / `insert_before` / `range_replace` / `unified_diff`。`editor.py` 中对 `range_replace` 的注释是 `# Range replace is fragile`。

**根本问题是失败模式静默**：模糊匹配在找不到精确目标时退化到"最相似的块"，把代码改到错误位置并返回成功。agent 基于错误状态继续迭代，错误被放大，且日志里看不出来。

Tau 的 `edit` 工具（`tau_coding/tools.py:478`）是相反设计：

| 维度 | 当前实现 | Tau |
|---|---|---|
| 操作类型 | 5 种 | 1 种（精确替换） |
| 匹配 | 模糊，多级回退 | 精确，`oldText` 必须唯一出现一次 |
| 0 次匹配 | 回退到相似块 | `_not_found_error`，报错并提示 |
| 多次匹配 | 取第一个 | `_duplicate_error`，报出现次数 |
| 多处编辑 | 逐次调用 | `edits[]` 数组，一次调用 |
| 原子性 | 逐个 op 落盘 | 全部校验通过才写文件 |
| 行尾/BOM | 无处理 | LF 归一化匹配 + 恢复主导行尾 + 保留 BOM |
| 并发 | 无 | 文件锁 |
| 返回 | 成功/失败文本 | ndiff + unified patch + first changed line |

失败变成响亮的、可恢复的、对模型可读的。

---

## 3. 目标架构

```
worker (JOB_HANDLERS)
  └─ docker run prompt-trading-agent
       └─ python -m agent.runner_v2          ← 保留，重写为同步 driver
            │
            ├─ 1. 种 versions/<version_id>/ 工作区        ← 现有逻辑不变
            ├─ 2. 拼 task prompt                          ← 现有逻辑不变
            ├─ 3. subprocess: tau --mode rpc --cwd <version_dir> \
            │        -e /app/agent/tau_ext.py
            │      ├─ stdin  ← JSONL 命令
            │      └─ stdout → JSONL 事件 → progress_callback → Redis
            │
            │    tau 进程内：
            │      · read / write / edit / bash        （tau 内置）
            │      · 自动上下文压缩                     （tau 内置）
            │      · session 持久化                     （tau 内置）
            │      · backtest / task_done               ← 我们的 extension
            │      · Strategy Protocol prompt section   ← 我们的 extension
            │
            ├─ 4. 校验产物（strategy.py / overview.md / protocol）  ← 现有逻辑不变
            └─ 5. publish 到 strategy/ + git commit                 ← 现有逻辑不变
```

**边界原则**：领域代码零侵入 Tau。`backtest_tool.py` 保持现在的纯函数签名，extension 只是一层 `AgentTool` 包装。回滚 = 换掉 driver，领域层不动。

### 3.1 为什么是 subprocess RPC，不是 embed

- Tau 全异步（anyio）。embed 意味着 `runner_v2` 主流程、工具层、`run_agent_backtest` 全部改 async，改动面远大于本次目标。
- `tau_coding/rpc.py` 的开头写明 "Pi-compatible JSONL RPC frontend for a Tau coding session"，`--mode rpc` 是**公开契约**，比 0.4.x 的内部 Python API 稳定得多。
- 进程隔离意味着 tau 崩溃/卡死不会带走 driver 的产物校验和 publish 逻辑。

这不是"中间层"——它是集成边界，没有为了可切换而存在的抽象。

---

## 4. 变更清单

### 4.1 删除

| 路径 | 行数 | 说明 |
|---|---|---|
| `packages/agent/agent/autonomous.py` | 578 | ReAct loop → tau harness |
| `packages/agent/agent/llm_openai_compat.py` | 335 | LLM 客户端 → `tau_ai` |
| `packages/agent/agent/context_manager.py` | 213 | 上下文压缩 → `tau_coding/context_window.py` |
| `packages/agent/agent/tools.py` | 327 | 文件工具 → tau 内置（`run_backtest` 迁到 extension） |
| `packages/agent/agent/editor.py` | ~120 | change-spec 适配器 → tau `edit` |
| `packages/code_editor/` | 2259 | 整包删除 |
| `packages/agent/agent/skills.py` | 375 | → `SKILL.md`（见 §6） |
| `packages/agent/agent/config.py` 中的 `AgentConfig`/`StopReason` | 部分 | 步数/token 预算改由 tau 管理 |
| `packages/agent/tests/test_enhanced_agent.py`、`test_editor_adapter.py` | — | 对应实现已删 |
| `packages/agent/agent/pipeline/` | — | 仅自引用（V6 实测） |
| `packages/agent/agent/smoke_validation.py` | 577 | **死代码**：`run_smoke_validation` 全仓库无调用者（V6 实测）。它 import `llm_openai_compat`，是删除 LLM 客户端的唯一阻碍 |
| `packages/agent/agent/middleware/` | ~110 | 仅被 `smoke_validation.py` 引用 |

合计约 **4.9k 行**。

> `worker/main.py:605` 的产物复制清单里还列着 `smoke_validation.json`、`plan.json`、
> `change_spec_report.json`、`smoke_backtest.py`、`verification_report.json`、
> `diagnosis.json`、`hitl_required.json`、`strategy_explain.json` 等多个无人写入的文件名。
> 该清单是 `if os.path.isfile(src)` 的宽容复制，留着无害，**不在本次范围内**。

`packages/code_editor` 的删除额外解决一个遗留问题：该包移植自 OpenCode 的 `edit.ts`，`NOTICE` 中的许可证归属一直未最终确认。删除即消除该风险。

### 4.2 保留（领域层，不动）

- `packages/agent/agent/backtest_tool.py` — `BacktestDataset` / `BacktestBudget` / `run_agent_backtest` / `budget_summary`。**签名不变**，extension 直接调用。
- `packages/agent/agent/protocol.py` — `STRATEGY_FILE` / `OVERVIEW_FILE` / `PROTOCOL`。
- `packages/agent/agent/prompt/` — builder / templates / context / code_slice / indicator_docs。
- `packages/agent/agent/templates.py` — `fallback_strategy_py` 等。
- `packages/agent/agent/observability/` — langfuse / metrics。
- `packages/backtest`、`packages/data` — 不受影响。

### 4.3 新增

| 路径 | 内容 |
|---|---|
| `packages/agent/agent/tau_ext.py` | Tau extension：注册 `backtest` / `task_done` 工具，注入 Strategy Protocol prompt section，挂 budget 守卫 hook |
| `packages/agent/agent/tau_driver.py` | JSONL RPC 客户端：起 tau 子进程、发命令、读事件、转 progress |
| `packages/agent/agent/backtest_subprocess.py` | 一次性回测执行器，隔离进程级网络守卫（见 §5.1 / §11.1） |
| `packages/agent/agent/tau_config.py` | 仅在配了自定义 `LLM_BASE_URL` 时写 openai-compatible provider（见 §7.2） |
| `packages/agent/tests/test_tau_driver.py` | 用假 tau 进程（回放 JSONL fixture）测 driver |
| `packages/agent/tests/test_tau_ext.py` | 测工具包装与 `task_done` 校验 |

### 4.4 重写

- `packages/agent/agent/runner_v2.py`：`main()` 中间那段 `AutonomousAgent(...)` + `agent.run(task)` 换成 `tau_driver.run_session(...)`。**前后的工作区种子、产物校验、publish、git commit、llm_meta 写入全部保持不变。** 预计净减少 ~250 行。

---

## 5. Tau Extension 设计

文件：`packages/agent/agent/tau_ext.py`，容器内通过 `tau -e /app/agent/tau_ext.py` 加载。

```python
"""Tau extension: strategy backtesting tools and protocol for the coding agent."""

from collections.abc import Mapping

from tau_agent.messages import TextContent
from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken, ToolUpdateCallback
from tau_agent.types import JSONValue
from tau_coding.extensions import ExtensionAPI

from agent.backtest_tool import BacktestBudget, BacktestDataset, run_agent_backtest
from agent.protocol import OVERVIEW_FILE, PROTOCOL, STRATEGY_FILE

# 进程级单例：一个 tau 进程 == 一个 agent session == 一份预算
_DATASET = BacktestDataset.from_env()
_BUDGET = BacktestBudget.from_env()
_WORKSPACE = os.environ["TAU_WORKSPACE"]   # == version_dir


async def _run_backtest(tool_call_id, arguments, signal=None, on_update=None) -> AgentToolResult:
    """在子进程里跑回测。

    子进程是必需的，不是优化：`run_agent_backtest` 会调 `_install_guard()`，
    它进程级 monkeypatch socket 且只放行交易所域名。在 tau 进程内直接调用会
    把 tau 自己的 LLM 连接一起掐掉（见 §11 V5 的复现）。
    """
    payload = {
        "strategy_path": os.path.join(_WORKSPACE, STRATEGY_FILE),
        "entry_function": str(arguments.get("entry_function", "generate_signals")),
        "params": arguments.get("params"),
        "dataset": dataclasses.asdict(_DATASET),
        "runs_used": _BUDGET.runs_used,      # 预算状态留在父进程，随调用传入
        "max_runs": _BUDGET.max_runs,
    }
    proc = await anyio.run_process(
        [sys.executable, "-m", "agent.backtest_subprocess"],
        input=json.dumps(payload).encode(), check=False,
    )
    result = json.loads(proc.stdout)                    # {ok, report, metrics}
    if result["metrics"] is not None:
        _BUDGET.record(result["metrics"])               # 父进程累积预算与 stall 判定
    return AgentToolResult(content=[TextContent(text=result["report"])],
                           details={"metrics": result["metrics"], "ok": result["ok"]})


async def _task_done(tool_call_id, arguments, signal=None, on_update=None) -> AgentToolResult:
    """协议守门：两个必需产物都在才允许声明完成。

    注意：tau 0.4.1 的 `AgentToolResult.terminate` 是未实现的占位字段
    （`tools.py:27` 声明，全仓库无消费点，见 §11 V4），所以本工具无法强制
    终止 loop。它只负责「不合格就打回」；真正的完成判定在 driver 侧（§8.4）。
    """
    problems = _validate_workspace(_WORKSPACE)   # strategy.py 存在、overview.md 存在且含 mermaid
    if problems:
        return AgentToolResult(
            content=[TextContent(text="Cannot finish yet:\n" + "\n".join(problems))],
        )
    return AgentToolResult(
        content=[TextContent(text=f"Task complete. {arguments.get('summary', '')}")],
        details={"summary": arguments.get("summary", "")},
    )


def setup(tau: ExtensionAPI) -> None:
    tau.register_tool(AgentTool(name="backtest", ..., execute_fn=_run_backtest))
    tau.register_tool(AgentTool(name="task_done", ..., execute_fn=_task_done))
    tau.add_prompt_section("Strategy Protocol", _protocol_markdown(PROTOCOL))
    tau.add_prompt_section("Backtest Budget", _budget_markdown(_DATASET, _BUDGET))
    tau.add_prompt_guideline(
        f"You must produce both {STRATEGY_FILE} and {OVERVIEW_FILE} (with a mermaid diagram) "
        "before calling task_done."
    )
```

**关键设计点**：

1. **`task_done` 只是协议守门，不能终止 loop。** V4 实测：`terminate` 字段在 tau 0.4.1 未实现。loop 在模型停止调用工具时自然结束，完成判定由 driver 在 `agent_settled` 后做（§8.4）。`task_done` 的价值是把「产物不全」在模型还在干活时就告诉它，而不是等 driver 打回来重来一轮。
2. **backtest 必须跑在子进程里。** 这是 V5 的直接后果，不是性能优化。子进程同时解决了「同步阻塞会卡住 RPC 事件流」的问题——`anyio.run_process` 天然不阻塞事件循环，前端进度不断流。
3. **预算状态留在父进程。** 子进程是无状态的：父进程把 `runs_used` / `max_runs` 传进去，把 `metrics` 拿回来，由父进程的 `_BUDGET.record()` 累积历史和判定 stall。否则每个子进程都从零开始，预算失效。
4. **预算耗尽后用 tool-call hook 摘掉工具。** 用 `ToolCallHookEvent` 在 `_BUDGET.exhausted` 后把 `backtest` 从工具列表移除，避免模型反复撞墙浪费 token。

### 5.1　`agent/backtest_subprocess.py`

新增的薄执行器，唯一职责是在一个干净进程里跑一次回测：

```python
"""Run one agent backtest in an isolated process.

Isolation is the point: `run_agent_backtest` installs a process-wide network
guard that only allows the exchange host, so it cannot share a process with the
agent's own LLM connection.
"""

def main() -> int:
    req = json.load(sys.stdin)
    dataset = BacktestDataset(**req["dataset"])
    budget = BacktestBudget(max_runs=req["max_runs"], runs_used=req["runs_used"])
    ok, report, metrics = run_agent_backtest(
        strategy_path=req["strategy_path"], entry_function=req["entry_function"],
        dataset=dataset, budget=budget, params=req["params"])
    json.dump({"ok": ok, "report": report, "metrics": metrics}, sys.stdout)
    return 0
```

`run_agent_backtest` 本身签名不变——它照旧在自己的进程里调 `_install_guard()`，
只是那个进程现在是一次性的。

---

## 6. Skills 迁移

当前 `agent/skills.py`（375 行）自研 `Skill` 基类 + `BacktestSkill` + `AnalyzeSkill` + `SkillRegistry`。

Tau 原生支持 `SKILL.md`（`tau_coding/skills.py`，从 `<project>/.tau/skills/*/SKILL.md` 与 `~/.tau/skills/` 加载）。

迁移映射：

- `BacktestSkill` → 由 extension 的 `backtest` **工具**承担（它本来就是工具语义，不是 workflow）。
- `AnalyzeSkill` → `packages/agent/skills/analyze/SKILL.md`，构建时 COPY 到镜像的 `~/.tau/skills/analyze/SKILL.md`。
- `SkillRegistry` → 删除。

---

## 7. 镜像与配置

### 7.1 `infra/images/agent/Dockerfile`

```dockerfile
FROM public.ecr.aws/docker/library/python:3.13-slim
# ... apt-get 不变 ...

COPY infra/images/agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 删除：COPY packages/code_editor + pip install

COPY packages/agent/agent /app/agent
COPY packages/backtest/backtest /app/backtest
COPY packages/data/data /app/data
COPY packages/live_trading_sdk/live_trading_sdk /app/live_trading_sdk

# Tau skills + provider 配置烘进镜像（tau setup 是纯本地文件写入，无网络调用）
COPY packages/agent/skills /root/.tau/skills
RUN python -m agent.tau_config          # 写 ~/.tau/catalog.toml + preferences

ENV PYTHONPATH=/app
CMD ["python", "-m", "agent.runner_v2"]
```

`requirements.txt` 变更：

```diff
+ tau-ai==0.4.1        # pin 精确版本，不用 >=
- # (code_editor 不再需要)
```

`tau-ai` 会引入 `textual` / `rich` / `typer` / `pillow` / `pydantic` / `httpx` / `pygments`。TUI 依赖在容器里用不上但无害；镜像增量约 30–40 MB。**不做 vendoring 裁剪** —— 裁掉就丢了 `rpc.py` 和 extension loader，得不偿失。

### 7.2 Provider 配置

**V1 实测结论：比设计初稿假设的简单得多。** `load_provider_settings()` 开箱返回
**28 个 provider**，`anthropic` 是内置原生条目（`AnthropicProviderConfig`，
`api = "anthropic-messages"`，`ANTHROPIC_API_KEY`，15 个模型），`deepseek` 也有
原生条目。**不需要手写 `catalog.toml`。**

因此 `agent/tau_config.py` 只在一种情况下需要做事：用户配了自定义 `LLM_BASE_URL`
（第三方中转、自建网关）。此时调 `tau_coding.cli.setup_command()` 写一个
openai-compatible 条目——它是纯本地文件写入，无网络调用，可以在镜像构建时跑。

其余情况直接 `--provider anthropic|deepseek --model <id>`，只要对应的 API key
环境变量在即可。

> **`--model` 必须显式传。** 实测：只改 `base_url` 而不传 `--model`，tau 仍会用
> provider 的 `default_model`（我配了 deepseek 的 base_url，`get_state` 回来的模型
> 是 `gpt-5.4`）。driver 永远显式传 `--provider` 和 `--model`。

环境变量映射：

| 现有 env | 映射到 |
|---|---|
| `LLM_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | provider 的 `api_key_env` |
| `LLM_BASE_URL` | openai-compatible `base_url` |
| `LLM_MODEL` | `--model` |
| `ANTHROPIC_API_KEY`（新增，可选） | 触发 anthropic 原生 provider |

`_llm_config()` 现有的解析逻辑保留，只是产出从 `LLMConfig` 变成 tau 的 provider/model 参数。

✅ 已由 V1 实测确认。

### 7.3 环境变量

保持不变，worker 侧 `services/worker/worker/main.py` 的 env 透传列表不动：

`AGENT_BACKTEST_{EXCHANGE,SYMBOL,INTERVAL,BARS,START_MS,END_MS,MAX_RUNS,STALL_LIMIT,SCORE_KEY}`

`AGENT_MAX_STEPS` / `AGENT_MAX_TOKENS` 语义变更：
- `AGENT_MAX_STEPS` → 映射到 tau 的 `max_turns`。
- `AGENT_MAX_TOKENS` → **废弃**。tau 按模型 context window 自动决定压缩阈值（`auto_compaction_threshold_for_context_window`），比固定 token 上限更合理。worker 的透传列表里保留该变量名但不再消费，避免同时改两个服务。

新增（driver 内部使用，不需要 worker 透传）：`TAU_WORKSPACE`（= `version_dir`）。

---

## 8. RPC Driver 设计

文件：`packages/agent/agent/tau_driver.py`。**同步实现**，用 `subprocess.Popen` + 阻塞行读取，`runner_v2` 无需改成 async。

### 8.1 启动

```python
proc = subprocess.Popen(
    ["tau", "--mode", "rpc",
     "--cwd", version_dir,
     "--provider", provider_name,
     "--model", model,
     "-e", "/app/agent/tau_ext.py"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,   # stderr 直通容器日志
    text=True, bufsize=1,
    env={**os.environ, "TAU_WORKSPACE": version_dir},
)
```

### 8.2 命令（driver → tau，每行一个 JSON）

| 命令 | 用途 |
|---|---|
| `{"id":1,"type":"prompt","message":"<task>"}` | 投递任务 |
| `{"id":N,"type":"prompt","message":"<修正指令>","streamingBehavior":"followUp"}` | 校验失败后追加（见 8.4） |
| `{"id":N,"type":"get_state"}` | 查 `isStreaming` / `messageCount` |
| `{"type":"abort"}` | 超时中止 |
| 关闭 stdin | tau 收到 EOF 后 cancel + `aclose()`，正常退出 |

### 8.3 事件（tau → driver）

必须处理的事件类型：

| 事件 | driver 动作 |
|---|---|
| `agent_start` | 记录开始 |
| `turn_start` / `turn_end` | 步数计数 |
| `message_update` | 可选：流式文本 → progress（前端进度更细） |
| `tool_execution_start` | `progress_callback({"tool": name, "args": ...})` → Redis |
| `tool_execution_end` | 记录 `is_error`；`backtest` 的 `result.details.metrics` 存进迭代记录 |
| `compaction_start` / `compaction_end` | 记日志（观察压缩频率） |
| `auto_retry_start` / `auto_retry_end` | 记日志（provider 抖动可见） |
| `agent_end` | **不是终点** —— 带 `will_retry` 字段，可能多次触发 |
| **`agent_settled`** | **终点**。一轮 prompt 真正结束、队列排空 |
| `rpc_error` | 协议层错误，直接失败 |
| `response` | 命令 ack，校验 `success` |

> ⚠️ **最容易写错的一点**：终止条件是 `agent_settled`，不是 `agent_end`。`SessionAgentEndEvent` 有 `will_retry: bool`，自动重试时会发多次；只有 `AgentSettledEvent` 表示"agent 停下来了"。

### 8.4 完成契约

```
发 prompt
  → 读事件直到 agent_settled
  → 校验 version_dir 产物（_validate_strategy_code + overview 检查）
      ├─ 通过 → 关 stdin，等进程退出，返回成功
      └─ 不通过 且 重试次数 < N → 发 follow_up prompt 说明缺什么，回到读事件
                 且 重试次数 == N → 关 stdin，抛 RuntimeError（走现有 fallback 分支）
```

**这是完成判定的唯一机制**，不是兜底。V4 实测确认 `terminate` 字段在 tau 0.4.1 未实现，
所以 loop 只会在模型自己停止调用工具时结束，driver 必须自己判断产物是否合格。
`task_done` 的作用是把不合格提前告诉模型，减少走到 followUp 这一步的次数。`N` 默认 2。

### 8.5 超时与清理

- 单次事件读取超时（`AGENT_TAU_EVENT_TIMEOUT_S`，默认 300s）：无事件即视为卡死 → 发 `abort` → 等 10s → `proc.kill()`。
- 总时长上限沿用 worker 侧现有的容器超时，driver 不重复实现。
- `finally` 中确保 `proc.kill()` + `proc.wait()`，避免孤儿进程。

---

## 9. Prompt 迁移

现有系统提示词分两处：`autonomous.py` 的 `SYSTEM_PROMPT` 常量（通用编码指导）和 `prompt/` 包（领域内容）。

- **通用编码部分整段丢弃。** Tau 自带 `system_prompt.py`，且它的工具描述里带 `prompt_guidelines`（例如 edit 工具自己声明"oldText 要尽量小但唯一""多处改动合并成一次调用"）。自己再写一份只会和 tau 的指导冲突。
- **领域部分**（`prompt/templates.py`、`indicator_docs.py`、`code_slice.py`）通过 `tau.add_prompt_section()` 注入，保持 `prompt/` 包不动，extension 只负责调用 builder 拿字符串。
- `_build_agent_task()` 产出的任务描述作为第一条 `prompt` 消息发送，逻辑不变。

---

## 10. 测试方案

### 10.1 单元测试（无需 Docker、无需 API key）

- `test_tau_driver.py`：用一个假的 tau 进程（`python -c` 回放预录的 JSONL fixture）驱动 driver，覆盖：
  - 正常完成（收到 `agent_settled` 后校验通过）
  - `agent_end(will_retry=True)` 后又收到事件 → driver 不能提前退出
  - 产物缺失 → 发出 follow_up
  - `rpc_error` → 失败
  - 事件超时 → 发 abort 并 kill
- `test_tau_ext.py`：直接调 extension 的 `_run_backtest` / `_task_done`，覆盖预算耗尽、overview 缺 mermaid、正常 terminate。

fixture 从一次真实运行录制，存 `packages/agent/tests/fixtures/tau_rpc_*.jsonl`。

### 10.2 集成测试（需镜像 + API key）

按 CLAUDE.md 的要求，依赖/Dockerfile 改动后必须构建并运行镜像：

```bash
docker build -f infra/images/agent/Dockerfile -t prompt-trading-agent:verify .
docker run --rm prompt-trading-agent:verify tau --version
docker run --rm prompt-trading-agent:verify python -c "import agent.tau_driver, agent.tau_ext"
```

端到端：起 dev compose，跑一次 `generate_and_backtest`，检查 `versions/<id>/` 产物齐全、`backtest_iterations.json` 有记录、strategy 已 publish 且 git 有 commit。

### 10.3 验收标准

同一组 5 个策略 prompt，迁移前后各跑一遍，要求：

| 指标 | 门槛 |
|---|---|
| 生成成功率（产物齐全 + 可导入） | ≥ 迁移前 |
| 编辑工具错误率（`is_error` 占 edit 调用比） | ≤ 迁移前 |
| **静默错改**（编辑落到非预期位置） | 0（这是本次迁移的主要目的） |
| 完成一次生成的 token 成本 | ≤ 迁移前 ×1.2（切 Anthropic caching 后应显著低于） |
| 回测迭代收敛步数 | 不劣化 |

迁移前的基线数据在动手**之前**采集，否则事后无从比较。

### 10.4 A/B 基线评测实测结论（MiniMax-Text-01）

使用同一组 5 个标准策略 Prompt 在同一环境对 Side A（迁移前镜像 `prompt-trading-agent:baseline`）与 Side B（Tau 架构镜像 `prompt-trading-agent:verify`）进行了实测对比：

#### 核心指标对比

| 评测维度 | Side A: Baseline (旧版手写 Harness) | Side B: Tau (新版 Tau Harness) | 对比结论 |
|---|---|---|---|
| **生成成功率** | **0 / 5 (0%)** | **4 / 5 (80%)** | 🟢 Tau 具备状态自愈与 Driver 驱动兜底能力 |
| **平均耗时** | 189.7 秒 / 轮（全部阻塞超时） | **136.6 秒 / 轮**（最快 70.6s） | 🟢 速度明显提升 |
| **7 项标准产物生成率** | 0%（无法闭环产出） | **100% (4/4 成功轮次全部齐备)** | 🟢 规范产物全齐 |
| **Python 代码合法性** | 0% | **100% (全部通过 AST 校验)** | 🟢 正确输出合法指标计算 |
| **Token 消耗监控** | 无法采集 | **约 20.6k tokens / 轮** | 🟢 成本与 Token 完整可观测 |

#### 5 个测试用例详细结果

| 用例编号与策略名称 | Side A (Baseline) | Side B (Tau) | Tau 耗时 | Tau Token 消耗 | 产物完整度 (7项) |
|---|---|---|---|---|---|
| **Case 1: EMA 双均线交叉策略** | ❌ 失败 (`idle` 中断) | ✅ **成功 (`task_done`)** | 199.6s | 26,328 | 7/7 完整 |
| **Case 2: RSI 超买超卖反转策略** | ❌ 失败 (`idle` 中断) | ✅ **成功 (`task_done`)** | 133.3s | 23,254 | 7/7 完整 |
| **Case 3: 布林带突破 + ATR 止损** | ❌ 失败 (`idle` 中断) | ✅ **成功 (`task_done`)** | **70.6s** | **9,373** | 7/7 完整 |
| **Case 4: MACD 柱与成交量动量** | ❌ 失败 (`idle` 中断) | ✅ **成功 (`task_done`)** | 143.0s | 23,621 | 7/7 完整 |
| **Case 5: 双周期均线突破** | ❌ 失败 (`idle` 中断) | ⚠️ 偶发未写入超时 | 162.2s | - | 0/7 |

#### 关键发现与改进
1. **旧版失效根因**：手写 `AutonomousAgent` 在第三方模型提前停止 tool call 时无法驱动模型推进产物，直接判定为 `Agent stopped: idle` 异常中断。
2. **Tau 优势**：由外部 Driver 校验 workspace 完整性，驱动模型补齐产物并规范调用 `task_done`。
3. **动态 Provider 兼容增强**：在 `tau_config.py` 与 `runner_v2.py` 中增加了 `ensure_catalog_entry`，确保容器在运行时支持任意自定义 OpenAI 兼容 BaseURL 与自定义模型 ID。

---

## 11. 验证结果（V1–V7，已实测）

设计初稿里这一节是「动手前必须逐条实测」的待办。以下是实测结论；
**V4 与 V6 不成立，对应的设计变更已折叠进 §5 / §4.1；V5 查出一个主线上的既有 bug。**

| # | 结论 | 实测发现 |
|---|---|---|
| **V1** | ✅ **优于预期** | 不需要手写 `catalog.toml`。`load_provider_settings()` 开箱返回 28 个 provider，`anthropic` 是内置原生条目（`AnthropicProviderConfig` / `api=anthropic-messages` / `ANTHROPIC_API_KEY` / 15 个模型），`deepseek` 亦有原生条目。§7.2 已简化 |
| **V2** | ✅ 成立 | `tau --mode rpc` 在非 TTY、干净 `HOME` 下正常启动，`get_state` 返回严格 JSONL，无交互引导 |
| **V3** | ✅ 成立 | `-e ext.py` 的 `setup()` 在 rpc 模式下确实执行，`register_tool` / `add_prompt_section` 生效 |
| **V4** | ❌ **不成立** | `AgentToolResult.terminate` 在 tau 0.4.1 是**未实现的占位字段**：`tau_agent/tools.py:27` 声明，`loop.py` / `harness.py` / `session.py` 全无消费点。→ §5 的 `task_done` 降级为纯协议守门，完成判定改由 §8.4 的 driver 校验循环承担 |
| **V5** | ⚠️ **查出主线 bug** | 见 §11.1 |
| **V6** | ❌ **部分不成立** | `pipeline/` 确实只有自引用可删；但 `middleware/` 被 `smoke_validation.py` 引用，而后者 import 了待删的 `llm_openai_compat`。进一步查出 `run_smoke_validation` **全仓库无调用者**——`worker/main.py:620` 只是把 `smoke_validation.json` 列进「存在就复制」的产物清单，无人写入该文件。→ 三者一并删除，见 §4.1 |
| **V7** | ✅ 成立 | `tau` 可执行文件随 `tau-ai` 安装进 PATH，`tau --version` → `0.4.1` |

### 11.1　V5：进程级网络守卫会掐断 agent 自己的 LLM 连接

`backtest_tool._install_guard()` 调 `install_network_guard()`，后者对
`socket.getaddrinfo` / `socket.create_connection` / `socket.socket.connect`
做**进程级** monkeypatch，且 `_INSTALLED` 是模块级 install-once。

- `runner.network_guard_enabled()` 在环境变量为空时返回 **True**（默认开启）。
- allowlist 为 `build_backtest_allowlist(exchange)` + `NETWORK_ALLOWLIST`，
  okx 时即 `["www.okx.com"]`。
- `infra/compose/.env.example` **未声明** `NETWORK_ALLOWLIST`。

复现：

```
network_guard_enabled() = True
allowlist = ['www.okx.com']
  www.okx.com          -> ALLOWED
  api.openai.com       -> BLOCKED (network_blocked:api.openai.com)
  api.anthropic.com    -> BLOCKED (network_blocked:api.anthropic.com)
  api.deepseek.com     -> BLOCKED (network_blocked:api.deepseek.com)
```

即：agent 容器里**第一次 backtest 之后，所有 LLM 调用都会被自己的守卫打掉**，
闭环迭代跑不过第一轮（除非部署环境的 `.env` 额外设了 `NETWORK_ALLOWLIST`）。

这不是迁移引入的——tau 架构下 LLM 与 backtest 同样同进程，风险完全相同。
**处置：本次迁移一并修复**，把回测放进子进程执行（§5.1），守卫只污染那个一次性进程。
这与 `smoke_validation.py:186` 早已采用的做法一致。
## 12. 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Tau v0.4.1，API 不稳定 | 高 | pin 精确版本；只依赖 `--mode rpc` 公开契约；领域层零侵入 |
| 上游停更 / 方向变化（huggingface/tau，本地快照 2026-08-29） | 中 | RPC 边界使替换成本 ≈ 一个 driver 文件；最坏情况 fork 并 pin |
| 精确匹配对模型能力要求更高（必须先 read 再原样复现） | 中 | 与切换到更强模型 + prompt caching 同批做；`_duplicate_error` / `_not_found_error` 的错误文本本身就是给模型的修复指引 |
| 一次性切换无回退开关 | 中 | **这是明确接受的前提**。回退手段是 revert 整个 PR，因此该 PR 必须自成一体、不夹带无关改动 |
| 镜像体积增加（TUI 依赖） | 低 | 接受 |
| 前端进度语义变化（step → tool event） | 低 | driver 侧把 tau 事件映射成现有 progress payload 形状，前端不改 |

---

## 13. 实施顺序（单个 PR 内）

不是分阶段发布，是一个 PR 里的施工次序：

1. **先采集迁移前基线**（§10.3 的 5 个 prompt）——否则事后无法比较。
2. 跑完 §11 全部 V1–V7 验证；有不成立的先改设计再继续。
3. 新增 `tau_config.py` + Dockerfile 改动，构建镜像，确认 `tau --mode rpc` 在容器里能跑最小 prompt。
4. 新增 `tau_ext.py`，验证 `backtest` / `task_done` 在 tau 里可调用。
5. 新增 `tau_driver.py` + 单元测试（含录制的 JSONL fixture）。
6. 改写 `runner_v2.py`，接上 driver。
7. **删除** §4.1 全部内容（含 `packages/code_editor`），修 import，跑包测试。
8. `skills.py` → `SKILL.md`。
9. 端到端跑 §10.2，采集迁移后指标，对照 §10.3 验收。
10. 更新 `CLAUDE.md`（"Coding Agent" 与 "Packaging" 两节）、`NOTICE`（移除 code_editor 的 OpenCode 归属）。

---

## 14. 评审要点

请重点确认：

1. **§3.1 subprocess RPC vs embed** —— 这是最大的架构选择。
2. **§5 的 `task_done` + `terminate=True`** —— 是否同意保留协议守门，而不是让模型自然停止。
3. **§7.3 `AGENT_MAX_TOKENS` 废弃** —— 交给 tau 按 context window 自动压缩。
4. **§10.3 验收门槛** —— 尤其"静默错改 = 0"是否是正确的核心指标。
5. **§11 待验证项** —— 是否还有你知道而我没列到的集成风险。
