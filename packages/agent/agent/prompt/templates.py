"""
Prompt templates for agent LLM interactions.

All prompt templates are centralized here for easy management and versioning.
Each template is a Prompt instance with metadata.

Design:
- One prompt per use case
- Support for variable interpolation
- Clear separation of system and user messages
"""

from __future__ import annotations

from agent.prompt.base import Prompt, PromptMetadata, PromptVersion


# ============== Strategy Generation Prompts ==============

STRATEGY_GENERATION_NEW = Prompt(
    metadata=PromptMetadata(
        name="strategy_generation_new",
        version=PromptVersion.V2,
        description="Generate a new strategy from user request",
        tags=["generation", "backtest"],
        tokens_estimate=900,
    ),
    system_template="""You are a senior quant developer specializing in vectorized backtesting strategies.

**IMPORTANT**: Focus ONLY on the generate_signals() function for backtesting.
DO NOT include ExampleLiveStrategy class or any live trading code.

Your task: Generate a complete generate_signals(data, params) -> dict function.

**CRITICAL**: Return format MUST include:
- Required fields: target_weights, weight_reason
- Debug fields: 2-6 additional bar-aligned arrays (indicators, conditions, etc.)
- Optional protocol fields: protocol_version, decision_id, decision_ts, expires_at
- Optional multi-symbol format: targets = SYMBOL_TO_PAYLOAD_DICT

Example correct return:
```python
return {{
    "target_weights": target_weights,   # float array, length n, range [-1, 1]
    "weight_reason": [...],             # str list, length n
    "ma_fast": fast_ma.to_numpy(),     # DEBUG: indicator value
    "ma_slow": slow_ma.to_numpy(),     # DEBUG: indicator value
    "regime_long": regime_long.to_numpy(),     # DEBUG: bool condition
}}
```

**Common mistakes to avoid**:
- Do NOT return pandas Series; use .to_numpy()
- Do NOT include ExampleLiveStrategy class
- Do NOT omit the debug fields (2-6 required)
- Follow the exact function signatures and return types documented in {platform_info}; do not assume undocumented return structures

Requirements:
- Signature: generate_signals(data: pandas.DataFrame, params: dict) -> dict
- Use params.get(key, default) with safe defaults
- weight_reason: short stable strings like 'regime_long', 'reduce_risk', 'flip_short'
- Output ONLY Python code, no markdown
- See {platform_info} for available indicators and function signatures

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

{platform_info}

Generate the strategy now.
""",
)


STRATEGY_GENERATION_REFINE = Prompt(
    metadata=PromptMetadata(
        name="strategy_generation_refine",
        version=PromptVersion.V2,
        description="Modify existing strategy with minimal changes",
        tags=["refine", "backtest"],
        tokens_estimate=1000,
    ),
    system_template="""You are a senior quant developer. You will be given CURRENT strategy code.
Make MINIMAL, TARGETED changes to fulfill the user request.

**CRITICAL**:
- Preserve ALL existing logic that is NOT mentioned in the request
- Keep the same structure, variable names, and logic flow
- DO NOT rewrite or simplify the code unnecessarily

**Return format REQUIREMENTS**:
Your generate_signals MUST return a dict with:
- Required: target_weights, weight_reason
- Debug: 2-6 additional bar-aligned arrays (indicators, conditions, etc.)
- Optional protocol fields: protocol_version, decision_id, decision_ts, expires_at
- Optional multi-symbol format: targets = SYMBOL_TO_PAYLOAD_DICT

Example correct return:
```python
return {{
    "target_weights": target_weights,
    "weight_reason": [...],
    "ma_fast": fast_ma.to_numpy(),     # required debug field
    "ma_slow": slow_ma.to_numpy(),     # required debug field
}}
```

Hard requirements:
- Define: generate_signals(data: pandas.DataFrame, params: dict) -> dict
- Use params.get(key, default) with safe defaults
- No network access, no file I/O, deterministic
- Output ONLY Python code, no markdown
- Follow the exact function signatures and return types documented in {platform_info}; do not assume undocumented return structures

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

{platform_info}

CURRENT_STRATEGY_CODE:
```python
{current_code}
```

**Instructions**: Apply ONLY the requested changes while keeping everything else EXACTLY the same.
Return the complete modified strategy.py code.
""",
)


# ============== Spec Generation Prompts ==============

SPEC_GENERATION = Prompt(
    metadata=PromptMetadata(
        name="spec_generation",
        version=PromptVersion.V1,
        description="Generate structured strategy spec from user request",
        tags=["spec", "generation"],
        tokens_estimate=600,
    ),
    system_template="""You are a trading strategy spec compiler. Output STRICT JSON only, no markdown, no explanations.

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

CURRENT_STRATEGY_CODE (may be empty):
```python
{current_code}
```

Output JSON with this exact schema (all keys required):
{{
  "version": 1,
  "summary": "short title under 30 chars",
  "strategy_type": "trend_following|mean_reversion|momentum|breakout|other",
  "market": "binance|okx|us_stock|other",
  "interval": "1m|5m|15m|1h|4h|1d",
  "direction": "long|short|both",
  "indicators": [{{"id": "fast_ma", "name": "sma|ema|rsi|zscore", "args": {{"window": 20}}}}],
  "entry_rules": ["..."],
  "exit_rules": ["..."],
  "params": [{{"name": "fast_window", "type": "int|float|bool|str", "default": 20, "min": 2, "max": 200}}],
  "risk": {{"max_weight": 1.0, "stop_loss": "", "take_profit": "", "time_exit": ""}},
  "debug_series": ["fast_ma", "slow_ma", "entry_cond"]
}}

Rules:
- Keep rules aligned with USER_REQUEST.
- Use 2-6 debug_series; they must correspond to indicators or entry/exit conditions.
- Use safe defaults in params.
- If CURRENT_STRATEGY_CODE exists, preserve its intent and only reflect requested changes.
""",
)


# ============== Plan Generation Prompts ==============

PLAN_GENERATION = Prompt(
    metadata=PromptMetadata(
        name="plan_generation",
        version=PromptVersion.V2,  # Updated to V2 with semantic operations
        description="Generate structured delivery plan with AST-based code analysis",
        tags=["planning", "delivery"],
        tokens_estimate=800,
    ),
    system_template="""You are a planner for quantitative strategy delivery.
Output STRICT JSON only. Keep all keys in English and match the schema exactly.

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

AVAILABLE_FUNCTIONS (select which function(s) to modify):
{function_signatures}

STRATEGY_PROTOCOL:
{protocol}

PLATFORM_CAPABILITIES:
{platform_info}

PARAMS_SCHEMA:
{params_schema}

Output JSON with this schema (all keys required):
{{
  "version": 1,
  "goal": {{
    "strategy_logic": "...",
    "symbol": "...",
    "interval": "...",
    "signals": "target_weights",
    "risk": "...",
    "positioning": "...",
    "cost_model": "..."
  }},
  "targets": {{
    "files": ["strategy.py", "strategy_spec.yaml", "backtest_config.json", "README.md"],
    "functions": ["generate_signals"]  # List which functions will be modified
  }},
  "interface_constraints": {{
    "required_function": "generate_signals",
    "input_columns": ["timestamp", "open", "high", "low", "close", "volume"],
    "output_required_series": ["target_weights", "weight_reason"],
    "debug_series": {{"min": 2, "max": 6}}
  }},
  "change_spec": {{
    "version": 2,
    "operations": [
      {{
        "type": "semantic_edit",  // New: semantic-level operation
        "function_name": "generate_signals",  // Which function to modify
        "anchor": "fast_ma = sma(close, params['fast'])",  // A unique line to locate the edit position
        "change_description": "Add RSI risk guard: force target_weights to 0 when RSI > 80",  // What to change (in English)
        "new_code_snippet": "rsi_val = rsi(close, 14)\\ntarget_weights = np.where(rsi_val > 80, 0.0, target_weights)"  // The new code to insert
      }}
    ]
  }},
  "deliverables": {{
    "files": ["strategy.py", "strategy_spec.yaml", "params_schema.json", "strategy_meta.json", "strategy_explain.json", "README.md"],
    "default_params": {{}},
    "smoke_test": {{"type": "synthetic_backtest", "n_bars": 200, "interval": "1h"}}
  }},
  "validation_steps": ["static_check", "lint", "mypy", "pytest", "smoke_backtest", "real_backtest"],
  "acceptance_criteria": ["strategy module imports", "required fields present", "dry-run backtest completes"],
  "risks": ["no_live_trading", "no_network_access", "deterministic_only"]
}}

Rules:
- Review AVAILABLE_FUNCTIONS and select which one(s) to modify
- function_name MUST be one of the available functions
- anchor MUST be a unique, identifiable line from the function (used for positioning)
- change_description: clearly describe what change to make
- new_code_snippet: the actual code to insert/replace (keep it concise)
- For new strategies (no existing code): set operations to [] and let the LLM generate fresh code
- If no changes needed: set operations to []
- Multiple operations are allowed if modifying different parts
""",
)


# Legacy V1 prompt (kept for backward compatibility)
PLAN_GENERATION_V1 = Prompt(
    metadata=PromptMetadata(
        name="plan_generation_v1",
        version=PromptVersion.V1,
        description="Generate structured delivery plan (legacy)",
        tags=["planning", "delivery", "legacy"],
        tokens_estimate=600,
    ),
    system_template="""You are a planner for quantitative strategy delivery.
Output STRICT JSON only. Keep all keys in English and match the schema exactly.

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

CURRENT_STRATEGY_CODE (trimmed):
```python
{code_preview}
```

STRATEGY_PROTOCOL:
{protocol}

PLATFORM_CAPABILITIES:
{platform_info}

PARAMS_SCHEMA:
{params_schema}

Output JSON with this schema (all keys required):
{{
  "version": 1,
  "goal": {{
    "strategy_logic": "...",
    "symbol": "...",
    "interval": "...",
    "signals": "target_weights",
    "risk": "...",
    "positioning": "...",
    "cost_model": "..."
  }},
  "targets": {{
    "files": ["strategy.py", "strategy_spec.yaml", "backtest_config.json", "README.md"],
    "functions": [{{"file": "strategy.py", "name": "generate_signals", "signature": "...", "behavior": "..."}}]
  }},
  "interface_constraints": {{
    "required_function": "generate_signals",
    "input_columns": ["timestamp", "open", "high", "low", "close", "volume"],
    "output_required_series": ["target_weights", "weight_reason"],
    "debug_series": {{"min": 2, "max": 6}}
  }},
  "change_spec": {{
    "version": 1,
    "operations": [
      {{
        "type": "exact_replace",
        "file_path": "strategy.py",
        "old_text": "...",
        "new_text": "...",
        "description": "..."
      }}
    ]
  }},
  "deliverables": {{
    "files": ["strategy.py", "strategy_spec.yaml", "params_schema.json", "strategy_meta.json", "strategy_explain.json", "README.md"],
    "default_params": {{}},
    "smoke_test": {{"type": "synthetic_backtest", "n_bars": 200, "interval": "1h"}}
  }},
  "validation_steps": ["static_check", "lint", "mypy", "pytest", "smoke_backtest", "real_backtest"],
  "acceptance_criteria": ["strategy module imports", "required fields present", "dry-run backtest completes"],
  "risks": ["no_live_trading", "no_network_access", "deterministic_only"]
}}

Rules:
- change_spec.operations MUST use type "exact_replace" only.
- file_path MUST be "strategy.py".
- old_text MUST be copied exactly from CURRENT_STRATEGY_CODE.
- If no change is needed, set operations to [].
- The indicators list is non-exhaustive. Custom indicators are allowed if they pass validation.
""",
)


# ============== Code Repair Prompts ==============

CODE_REPAIR_VALIDATION = Prompt(
    metadata=PromptMetadata(
        name="code_repair_validation",
        version=PromptVersion.V2,
        description="Repair code based on validation failure",
        tags=["repair", "validation"],
        tokens_estimate=800,
    ),
    system_template="""You are a senior quant developer. Fix the strategy code to pass smoke validation.

Rules:
- Make MINIMAL changes to fix the reported issue.
- Preserve existing logic unless required for correctness.
- Keep generate_signals signature and vectorized pandas/numpy.
- Output ONLY Python code (no markdown).

**CRITICAL for debug_series errors:**
Your return dict MUST have 2-6 EXTRA fields beyond the required ones:
- Required: target_weights, weight_reason
- Debug (2-6 examples): ma_fast, ma_slow, rsi, regime_long, regime_short, etc.
- All debug arrays must be bar-aligned (same length as data)

Example return structure:
```python
return {{
    "target_weights": target_weights,  # float array in [-1, 1], length n
    "weight_reason": [...],            # list of strings, length n
    "ma_fast": fast_ma.to_numpy(),    # DEBUG: required!
    "ma_slow": slow_ma.to_numpy(),    # DEBUG: required!
    "rsi": rsi.to_numpy(),            # DEBUG: optional
}}
```

{language_directive}
""",
    user_template="""USER_REQUEST:
{prompt}

VALIDATION_SUMMARY:
{validation}

CURRENT_CODE:
```python
{code}
```

Fix the issues and return the complete repaired code.
""",
)


# ============== Plan Decision Prompts ==============

PLAN_DECISION = Prompt(
    metadata=PromptMetadata(
        name="plan_decision",
        version=PromptVersion.V1,
        description="Decide whether to generate a structured plan",
        tags=["decision", "planning"],
        tokens_estimate=200,
    ),
    system_template="""You decide whether a structured delivery plan is necessary for this request.
Output STRICT JSON only.""",
    user_template="""USER_REQUEST:
{prompt}

CURRENT_STRATEGY_CODE (trimmed):
```python
{current_code}
```

Output JSON with this schema:
{{"should_plan": true|false, "reason": "short explanation"}}
""",
)


# ============== Deprecated/Compatibility Prompts ==============
# These are kept for backward compatibility during migration

REFINE_SYSTEM_PROMPT = STRATEGY_GENERATION_REFINE.system_template
REFINE_USER_TEMPLATE = STRATEGY_GENERATION_REFINE.user_template


__all__ = [
    # Strategy generation
    "STRATEGY_GENERATION_NEW",
    "STRATEGY_GENERATION_REFINE",
    # Spec generation
    "SPEC_GENERATION",
    # Plan generation
    "PLAN_GENERATION",
    # Repair
    "CODE_REPAIR_VALIDATION",
    # Decision
    "PLAN_DECISION",
    # Compatibility
    "REFINE_SYSTEM_PROMPT",
    "REFINE_USER_TEMPLATE",
]
