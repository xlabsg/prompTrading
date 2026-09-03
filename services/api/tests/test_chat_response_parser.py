from __future__ import annotations

from control_plane.enums import ChatStatus
import app.routers.strategies as strategies_router
from app.routers.strategies import _clean_summary_source_text, _is_summary_noise, _parse_chat_response, _summarize_chat_reply


def test_parse_ready_fenced_json_strips_protocol_preamble() -> None:
    reply = (
        "[READY]\n"
        "Here is the JSON requested:\n"
        "```json\n"
        '{"summary":"EMA Crossover","symbol":"BTC-USDT-SWAP"}\n'
        "```\n"
    )

    status, clean_reply, config = _parse_chat_response(reply)

    assert status == ChatStatus.READY
    assert isinstance(config, dict)
    assert config.get("summary") == "EMA Crossover"
    assert "Here is the JSON requested" not in clean_reply
    assert clean_reply == "I've gathered all the information needed. Here's the strategy configuration for your review:"


def test_parse_ready_keeps_user_facing_text_and_removes_noise() -> None:
    reply = (
        "[READY]\n"
        "Below is the JSON:\n"
        "请确认下面配置后生成策略。\n"
        "```json\n"
        '{"summary":"RSI Mean Reversion","symbol":"ETH-USDT-SWAP"}\n'
        "```\n"
    )

    status, clean_reply, config = _parse_chat_response(reply)

    assert status == ChatStatus.READY
    assert isinstance(config, dict)
    assert config.get("summary") == "RSI Mean Reversion"
    assert "Below is the JSON" not in clean_reply
    assert clean_reply == "请确认下面配置后生成策略。"


def test_parse_ready_plain_json_without_fence() -> None:
    reply = (
        "[READY]\n"
        "Here is the JSON requested:\n"
        '{"summary":"Breakout","symbol":"SOL-USDT-SWAP","interval":"4h"}'
    )

    status, clean_reply, config = _parse_chat_response(reply)

    assert status == ChatStatus.READY
    assert isinstance(config, dict)
    assert config.get("summary") == "Breakout"
    assert "Here is the JSON requested" not in clean_reply
    assert clean_reply == "I've gathered all the information needed. Here's the strategy configuration for your review:"


def test_parse_ready_answer_wrapped_json() -> None:
    reply = (
        "[READY]\n"
        '{"answer":"Here is the JSON requested: {\\"summary\\": \\"Trend Follow\\", \\"symbol\\": \\"BTC-USDT-SWAP\\"}"}'
    )

    status, clean_reply, config = _parse_chat_response(reply)

    assert status == ChatStatus.READY
    assert isinstance(config, dict)
    assert config.get("summary") == "Trend Follow"
    assert "Here is the JSON requested" not in clean_reply
    assert clean_reply == "I've gathered all the information needed. Here's the strategy configuration for your review:"


def test_parse_chatting_unchanged_when_not_ready() -> None:
    reply = "Here is the JSON requested: {\"note\":\"this is normal chat content\"}"

    status, clean_reply, config = _parse_chat_response(reply)

    assert status == ChatStatus.CHATTING
    assert clean_reply == reply
    assert config is None


def test_clean_summary_source_text_strips_protocol_and_json() -> None:
    raw = (
        "Here is the JSON requested:\n"
        "```json\n"
        '{"summary":"Trend Follow","symbol":"BTC-USDT-SWAP"}\n'
        "```\n"
        "请确认后生成策略。"
    )
    cleaned = _clean_summary_source_text(raw)
    assert "Here is the JSON requested" not in cleaned
    assert "summary" not in cleaned
    assert cleaned == "请确认后生成策略。"


def test_is_summary_noise_detects_json_protocol_noise() -> None:
    assert _is_summary_noise("Here is the JSON requested")
    assert _is_summary_noise('{"summary":"abc"}')
    assert not _is_summary_noise("已完成参数整理，请确认后生成策略。")


def test_summarize_chat_reply_retries_when_first_summary_is_noise(monkeypatch) -> None:
    monkeypatch.setattr(
        strategies_router,
        "_get_llm_config",
        lambda: ("dummy-key", "https://example.com/v1", "dummy-model"),
    )
    monkeypatch.setattr(strategies_router, "_get_llm_http_timeout_s", lambda: 1.0)

    responses = iter(
        [
            '{"summary":"Here is the JSON requested"}',
            '{"summary":"已提炼策略配置，下一步可确认并生成策略代码。"}',
        ]
    )

    def fake_post(*args, **kwargs):
        content = next(responses)

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return _Resp()

    monkeypatch.setattr(strategies_router.requests, "post", fake_post)

    summary = _summarize_chat_reply("请帮我整理策略并输出最终配置。")
    assert summary == "已提炼策略配置，下一步可确认并生成策略代码。"


def test_summarize_chat_reply_falls_back_to_cleaned_source_when_all_attempts_bad(monkeypatch) -> None:
    monkeypatch.setattr(
        strategies_router,
        "_get_llm_config",
        lambda: ("dummy-key", "https://example.com/v1", "dummy-model"),
    )
    monkeypatch.setattr(strategies_router, "_get_llm_http_timeout_s", lambda: 1.0)

    def fake_post(*args, **kwargs):
        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": '{"summary":"Here is the JSON requested"}'}}]}

        return _Resp()

    monkeypatch.setattr(strategies_router.requests, "post", fake_post)

    summary = _summarize_chat_reply(
        "[READY]\nHere is the JSON requested:\n```json\n{\"summary\":\"x\"}\n```\n请确认后生成策略。"
    )
    assert summary == "请确认后生成策略。"


def test_parse_ready_without_json_falls_back_to_chatting() -> None:
    reply = "[READY]\n好的，请确认以上信息是否正确，或者您是否有其他需要调整的地方？"
    status, clean_reply, config = _parse_chat_response(reply)
    assert status == ChatStatus.CHATTING
    assert config is None
    assert "请确认以上信息是否正确" in clean_reply
    assert "[READY]" not in clean_reply


def test_format_metrics_comparison_emits_structured_action_block() -> None:
    import json
    from app.routers.strategies import _format_metrics_comparison

    before = {"total_return": 0.10, "sharpe_ratio": 1.20, "max_drawdown": 0.08, "win_rate": 0.50}
    after = {"total_return": 0.18, "sharpe_ratio": 1.85, "max_drawdown": 0.05, "win_rate": 0.62}

    output = _format_metrics_comparison(before, after)
    assert "```action:metrics_comparison" in output
    assert "BTC-USDT-SWAP" in output

    # Extract JSON and verify fields
    json_str = output.split("```action:metrics_comparison\n")[1].split("\n```")[0]
    data = json.loads(json_str)
    assert data["benchmark"]["symbol"] == "BTC-USDT-SWAP"
    assert data["before"]["total_return"] == 0.10
    assert data["after"]["total_return"] == 0.18


def test_infer_dataset_from_prompt_variants() -> None:
    from app.routers.backtests import _infer_dataset_from_prompt

    # 1. US Stock AAPL 1d
    ds1 = _infer_dataset_from_prompt("请帮我写一个苹果 AAPL 的日线趋势跟踪策略")
    assert ds1.exchange == "us_stock"
    assert ds1.symbol == "AAPL"
    assert ds1.interval == "1d"

    # 2. Crypto ETH 15m
    ds2 = _infer_dataset_from_prompt("开发一个以太坊 ETH 15分钟突破策略")
    assert ds2.exchange == "okx"
    assert ds2.symbol == "ETH-USDT-SWAP"
    assert ds2.interval == "15m"

    # 3. Crypto SOL 4h
    ds3 = _infer_dataset_from_prompt("写一个 SOL 4小时均线策略")
    assert ds3.exchange == "okx"
    assert ds3.symbol == "SOL-USDT-SWAP"
    assert ds3.interval == "4h"

    # 4. Fallback default benchmark
    ds4 = _infer_dataset_from_prompt("写一个双均线金叉死叉策略")
    assert ds4.exchange == "okx"
    assert ds4.symbol == "BTC-USDT-SWAP"
    assert ds4.interval == "1h"
