# Prompt 生成重构实现总结

> **历史记录（截至 2026-09-02 之前）。** 本文描述的是当时的 prompt/pipeline 体系，
> 其中 `BasicPipeline`、`spec_pipeline`、`plan_builder`、`test_imports` 等已被删除，
> `runner_v2` 也已改为驱动 `AutonomousAgent`。当前架构见仓库根目录 `CLAUDE.md`
> 与 `docs/MVP_REFACTOR_PLAN.md`；本文仅作变更历史保留，不要据此写代码。

## 已完成的模块

### 1. Prompt 模块 (`agent/prompt/`)

| 文件 | 功能 |
|------|------|
| `base.py` | Prompt 基础类、PromptMetadata、PromptVersion |
| `templates.py` | 所有 prompt 模板集中定义 |
| `context.py` | 语言检测、智能代码截断、平台信息格式化 |
| `builder.py` | Prompt 构建器，统一构建入口 |
| `registry.py` | Prompt 注册表，支持版本管理和 A/B 测试 |

### 2. Observability 模块 (`agent/observability/`)

| 文件 | 功能 |
|------|------|
| `langfuse_client.py` | Langfuse 客户端封装（可选、单例、降级处理） |
| `metrics.py` | Token 使用、成本计算、Session 指标聚合 |
| `tracer.py` | LLM 调用追踪，Trace/Span 管理 |

### 3. Pipeline 模块 (`agent/pipeline/`)

| 文件 | 功能 |
|------|------|
| `base.py` | PipelineConfig、PipelineResult、工具函数 |
| `basic.py` | 基础 Pipeline（无 observability 开销） |
| `enhanced.py` | 增强版 Pipeline（带追踪和指标收集） |

### 4. Middleware 模块 (`agent/middleware/`)

| 功能 | 说明 |
|------|------|
| `should_generate_plan()` | 用规则替代 LLM 调用判断是否需要生成 plan |
| `decide_smoke_settings()` | 用规则决定 smoke 测试配置 |
| `detect_language()` | 快速语言检测 |

### 5. 新的 Runner (`agent/runner_v2.py`)

使用新架构的 runner 实现：
- PromptBuilder 构建 prompt
- LLMMiddleware 减少冗余调用
- SessionMetrics 追踪成本
- Langfuse 集成（可选）

### 6. 测试脚本 (`agent/test_imports.py`)

验证所有模块可以正确导入和运行。

---

## 主要改进对比

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| Prompt 位置 | 分散在 6 个文件 | 集中在 `prompt/templates.py` |
| 代码截断 | 简单字符数限制 | AST 智能保留关键部分 |
| 语言检测 | 仅 Unicode 范围 | 关键词 + Unicode |
| Plan 决策 | LLM 调用 | 规则判断（更快、更便宜） |
| 可观测性 | 无 | Langfuse 集成、成本追踪 |
| 版本管理 | 无 | 完整版本系统 + A/B 测试支持 |

---

## 环境变量

```bash
# Langfuse (可选)
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_HOST=https://cloud.langfuse.com

# Session 关联
STRATEGY_ID=strategy_123
USER_ID=user_456
```

---

## 使用示例

### 基础使用（无 observability）
```python
from agent.pipeline import BasicPipeline, PipelineConfig
from agent.prompt import PromptBuilder

config = PipelineConfig(
    api_key="sk-xxx",
    base_url="https://api.openai.com/v1",
    model="gpt-4o-mini",
    temperature=0.2,
)

pipeline = BasicPipeline(config)
result = pipeline.run(
    prompt="Create a MA crossover strategy",
    current_code="",
    platform_capabilities=_platform_capabilities(),
)
```

### 增强使用（带 observability）
```python
from agent.pipeline import EnhancedPipeline
from agent.observability import SessionMetrics

session_metrics = SessionMetrics(session_id="strategy_123")
pipeline = EnhancedPipeline(
    config=config,
    session_metrics=session_metrics,
)

result = pipeline.run(
    prompt="Create a MA crossover strategy",
    current_code="",
    platform_capabilities=_platform_capabilities(),
)

# 查看摘要
print(session_metrics.summary())
```

---

## 迁移路径

1. **阶段 1**：新模块与旧代码共存（当前状态）
2. **阶段 2**：逐步在现有 pipeline 中使用 PromptBuilder
3. **阶段 3**：用 LLMMiddleware 替换 `should_generate_plan()` LLM 调用
4. **阶段 4**：启用 observability（设置 Langfuse 环境变量）
5. **阶段 5**：完全切换到新的 runner_v2

---

## 依赖更新

`infra/images/agent/requirements.txt`:
```
+ langfuse>=2.0.0  # 可选 observability
```

---

## 下一步

- [ ] 在现有 `spec_pipeline.py` 中使用 PromptBuilder
- [ ] 用 LLMMiddleware 替换 `plan_builder.py` 中的 LLM 调用
- [ ] 添加更多 prompt 模板变体用于 A/B 测试
- [ ] 在 Langfuse Dashboard 中分析效果
