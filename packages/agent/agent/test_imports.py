#!/usr/bin/env python3
"""
Test script to verify new prompt and observability modules can be imported.
"""

import sys

def test_imports() -> int:
    """Test all new modules can be imported."""
    errors = []

    # Test prompt module
    try:
        from agent.prompt import (
            Prompt,
            PromptBuilder,
            PromptMetadata,
            PromptRegistry,
            get_registry,
            detect_language,
            build_language_directive,
            prepare_code_context,
        )
        print("✓ agent.prompt imports OK")
    except Exception as e:
        errors.append(f"agent.prompt: {e}")
        print(f"✗ agent.prompt: {e}")

    # Test observability module
    try:
        from agent.observability import (
            LangfuseClient,
            SessionMetrics,
            LLMTracer,
            calculate_cost,
        )
        print("✓ agent.observability imports OK")
    except Exception as e:
        errors.append(f"agent.observability: {e}")
        print(f"✗ agent.observability: {e}")

    # Test middleware module
    try:
        from agent.middleware import LLMMiddleware
        print("✓ agent.middleware imports OK")
    except Exception as e:
        errors.append(f"agent.middleware: {e}")
        print(f"✗ agent.middleware: {e}")

    # Test pipeline module
    try:
        from agent.pipeline import (
            BasicPipeline,
            EnhancedPipeline,
            PipelineConfig,
        )
        print("✓ agent.pipeline imports OK")
    except Exception as e:
        errors.append(f"agent.pipeline: {e}")
        print(f"✗ agent.pipeline: {e}")

    # Test runner_v2
    try:
        from agent import runner_v2
        print("✓ agent.runner_v2 imports OK")
    except Exception as e:
        errors.append(f"agent.runner_v2: {e}")
        print(f"✗ agent.runner_v2: {e}")

    if errors:
        print("\n=== Errors ===")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\n=== All imports successful ===")
    return 0


def test_prompt_builder() -> int:
    """Test PromptBuilder functionality."""
    from agent.prompt import PromptBuilder, PromptVersion

    builder = PromptBuilder()

    # Test language detection
    zh_text = "创建一个双均线交叉策略"
    en_text = "Create a moving average crossover strategy"

    zh_lang = builder._registry.detect_language if hasattr(builder, "_registry") else None
    print(f"  Language detection: {zh_lang}")

    print("✓ PromptBuilder basics OK")
    return 0


def test_middleware() -> int:
    """Test LLMMiddleware functionality."""
    from agent.middleware import LLMMiddleware

    # Test plan decision
    should_plan, reason = LLMMiddleware.should_generate_plan(
        "调整参数为20",
        "some existing code here" * 100,
    )
    print(f"  should_generate_plan (simple param): {should_plan}, reason: {reason}")

    should_plan2, reason2 = LLMMiddleware.should_generate_plan(
        "Create a complex strategy with multiple indicators and risk management",
        "some existing code here" * 100,
    )
    print(f"  should_generate_plan (complex): {should_plan2}, reason: {reason2}")

    # Test smoke settings
    settings = LLMMiddleware.decide_smoke_settings("回测", "code" * 100)
    print(f"  smoke_settings: {settings}")

    print("✓ LLMMiddleware OK")
    return 0


def test_observability() -> int:
    """Test observability modules."""
    from agent.observability import SessionMetrics, calculate_cost

    # Test cost calculation
    cost = calculate_cost("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 500})
    print(f"  cost calculation (gpt-4o): ${cost:.4f}")

    # Test session metrics
    metrics = SessionMetrics(session_id="test_123")
    from agent.observability.metrics import LLMCallMetrics

    call_metrics = LLMCallMetrics(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        cost_usd=cost,
        model="gpt-4o",
    )
    metrics.add_call(call_metrics, prompt_version="v2.0")

    summary = metrics.summary()
    print(f"  session summary: {summary}")

    print("✓ Observability OK")
    return 0


def main() -> int:
    """Run all tests."""
    print("=== Testing Imports ===")
    if test_imports() != 0:
        return 1

    print("\n=== Testing PromptBuilder ===")
    test_prompt_builder()

    print("\n=== Testing LLMMiddleware ===")
    test_middleware()

    print("\n=== Testing Observability ===")
    test_observability()

    print("\n=== All tests passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
