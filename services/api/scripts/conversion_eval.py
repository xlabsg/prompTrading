#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from control_plane.db import create_db_engine, create_session_factory
from control_plane.models import User, UserSession


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hour_floor_ms(ts_ms: int) -> int:
    return (ts_ms // 3_600_000) * 3_600_000


def _last_30d_range_ms() -> tuple[int, int]:
    now_ms = int(time.time() * 1000)
    end_ms = _hour_floor_ms(now_ms)
    start_ms = end_ms - 30 * 24 * 3_600_000
    return start_ms, end_ms


@dataclass(frozen=True)
class Case:
    url: str
    label: str


def _default_api_base_url() -> str:
    return (
        os.getenv("E2E_API_BASE_URL")
        or os.getenv("API_BASE_URL")
        or os.getenv("APP_PUBLIC_BASE_URL")
        or "http://api:8000"
    ).rstrip("/")


def _create_ephemeral_session_cookie() -> str:
    """Create an authenticated session by inserting a test user/session into DB (for local stacks)."""
    db_url = os.getenv("APP_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("missing_env:APP_DB_URL (or provide ASP_SESSION/EVAL_ASP_SESSION)")

    engine = create_db_engine(db_url)
    session_factory = create_session_factory(engine)

    token = secrets.token_urlsafe(32)
    suffix = secrets.token_hex(4)

    with session_factory() as db:
        user = User(
            email=f"conversion_eval_{suffix}@example.com",
            name=f"Conversion Eval {suffix}",
            is_active=True,
            created_at=_utcnow(),
        )
        db.add(user)
        db.flush()
        db.add(
            UserSession(
                user_id=user.id,
                token=token,
                expires_at=_utcnow() + timedelta(days=7),
                created_at=_utcnow(),
            )
        )
        db.commit()

    engine.dispose()
    return token


def _build_authed_http() -> requests.Session:
    sess = requests.Session()
    cookie = os.getenv("ASP_SESSION") or os.getenv("EVAL_ASP_SESSION")
    if not cookie:
        cookie = _create_ephemeral_session_cookie()
    sess.cookies.set("asp_session", cookie)
    return sess


def _request_json(
    sess: requests.Session,
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    timeout_s: int = 60,
) -> dict:
    resp = sess.request(method, url, json=payload, timeout=timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"http_{resp.status_code}:{resp.text}")
    return resp.json()


def _wait_job(sess: requests.Session, api_base_url: str, job_id: str, *, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    poll_s = 3.0
    while time.time() < deadline:
        job = _request_json(sess, "GET", f"{api_base_url}/api/jobs/{job_id}", timeout_s=30)
        if job.get("status") in ("succeeded", "failed"):
            return job
        time.sleep(poll_s)
        poll_s = min(15.0, poll_s + 1.5)
    raise TimeoutError(f"job_timeout:{job_id}")


def _wait_backtest_run(sess: requests.Session, api_base_url: str, run_id: str, *, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    poll_s = 3.0
    while time.time() < deadline:
        run = _request_json(sess, "GET", f"{api_base_url}/api/backtests/{run_id}", timeout_s=30)
        if run.get("status") in ("succeeded", "failed"):
            return run
        time.sleep(poll_s)
        poll_s = min(15.0, poll_s + 1.5)
    raise TimeoutError(f"backtest_timeout:{run_id}")


def _load_cases_file(path: str) -> list[Case]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and isinstance(obj.get("cases"), list):
        raw_cases = obj["cases"]
    elif isinstance(obj, list):
        raw_cases = obj
    else:
        raise ValueError("cases_file_invalid_format")

    cases: list[Case] = []
    for i, item in enumerate(raw_cases):
        if isinstance(item, str):
            url = item
            label = f"case_{i+1}"
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            label = str(item.get("label") or f"case_{i+1}")
        else:
            continue
        if not url:
            continue
        cases.append(Case(url=url, label=label))
    return cases


_FEED_JSON_HINT = re.compile(r"\"next\"\\s*:\\s*\"/scripts/page-\\d+/\"")


def _extract_feed_items_from_scripts_html(html: str) -> tuple[list[dict[str, Any]], str | None]:
    """Extract TradingView publication feed items embedded in HTML JSON."""
    best_items: list[dict[str, Any]] = []
    best_next: str | None = None

    # Many scripts tags exist; parsing everything is expensive. Narrow to the big feed blob.
    for m in re.finditer(
        r"<script[^>]*type=\"application/prs\\.init-data\\+json\"[^>]*>(.*?)</script>",
        html,
        re.DOTALL,
    ):
        raw = (m.group(1) or "").strip()
        if not raw or not _FEED_JSON_HINT.search(raw):
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        # DFS for {"items":[...], "next":"..."} containers.
        stack: list[Any] = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                items = cur.get("items")
                if isinstance(items, list) and items and all(isinstance(x, dict) for x in items):
                    score = sum(
                        1 for x in items if x.get("script_type") == "strategy" and x.get("script_access") == 1
                    )
                    if score and len(items) > len(best_items):
                        best_items = items  # type: ignore[assignment]
                        nxt = cur.get("next")
                        best_next = nxt if isinstance(nxt, str) else None
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)

    return best_items, best_next


def _cases_from_trending(*, max_count: int) -> list[Case]:
    """Dynamically pick N public/open strategies from TradingView.

    Prefer using the repo's `trending_scraper` (keeps parsing logic in one place).
    Fall back to a lightweight HTML-embedded JSON extraction if the package isn't available.
    """
    try:
        from trending_scraper.scraper import TradingViewTrendingScraper

        scraper = TradingViewTrendingScraper(rate_limit_delay=0.2, max_retries=3, timeout=30)
        items = scraper.scrape_trending("scripts", max_count=max_count, filter_crypto=False)
        out: list[Case] = []
        seen: set[str] = set()
        for it in items:
            if len(out) >= max_count:
                break
            url = str(it.get("url") or "").strip()
            if not url or "/script/" not in url or url in seen:
                continue
            seen.add(url)
            label = str(it.get("title") or it.get("name") or "tradingview_strategy").strip()[:80]
            out.append(Case(url=url, label=label))
        if out:
            return out
    except Exception:
        pass

    url = "https://www.tradingview.com/scripts/?script_type=strategies&script_access=open"
    headers = {"User-Agent": "Mozilla/5.0"}
    out: list[Case] = []
    next_url: str | None = url
    seen: set[str] = set()

    while next_url and len(out) < max_count:
        html = requests.get(next_url, headers=headers, timeout=30).text
        items, next_rel = _extract_feed_items_from_scripts_html(html)
        for it in items:
            if len(out) >= max_count:
                break
            if it.get("script_type") != "strategy" or it.get("script_access") != 1:
                continue
            chart_url = it.get("chart_url")
            if not isinstance(chart_url, str) or "/script/" not in chart_url:
                continue
            if chart_url in seen:
                continue
            seen.add(chart_url)
            name = str(it.get("name") or "tradingview_strategy").strip()[:80]
            out.append(Case(url=chart_url, label=name))
        next_url = urljoin("https://www.tradingview.com", next_rel) if next_rel else None

    return out


def _classify_failure(msg: str) -> str:
    s = (msg or "").lower()
    if "tradingview_scrape_failed" in s or "tradingview_scrape_error" in s:
        return "scrape_failed"
    if "agent_container_exit_code" in s:
        return "agent_failed"
    if "pinescript_conversion_failed" in s:
        return "conversion_failed"
    if "missing_generate_signals" in s:
        return "missing_generate_signals"
    if "banned_import" in s or "banned_call" in s:
        return "unsafe_code"
    if "http_" in s:
        return "http_failed"
    if "timeout" in s:
        return "timeout"
    return "unknown"


def _read_validation_json(workspaces_dir: str, strategy_id: str, version_id: str) -> Optional[dict[str, Any]]:
    path = os.path.join(workspaces_dir, strategy_id, "versions", version_id, "pinescript_validation.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base-url", default=_default_api_base_url())
    ap.add_argument("--cases-file", default="")
    ap.add_argument("--from-trending", type=int, default=0)
    ap.add_argument("--max-cases", type=int, default=0)
    ap.add_argument("--out", default="conversion_eval_report.json")
    ap.add_argument("--out-failures", default="conversion_eval_failures.json")
    ap.add_argument("--job-timeout", type=int, default=int(os.getenv("EVAL_JOB_TIMEOUT_S", "3600")))
    ap.add_argument("--backtest-timeout", type=int, default=int(os.getenv("EVAL_BACKTEST_TIMEOUT_S", "3600")))
    ap.add_argument("--skip-backtest", action="store_true")
    ap.add_argument("--assert-strategy-py", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    api_base_url = args.api_base_url.rstrip("/")
    sess = _build_authed_http()

    if args.from_trending > 0:
        cases = _cases_from_trending(max_count=args.from_trending)
    elif args.cases_file:
        cases = _load_cases_file(args.cases_file)
    else:
        raise SystemExit("Provide --from-trending N or --cases-file PATH")

    if args.max_cases and args.max_cases > 0:
        cases = cases[: args.max_cases]

    start_ms, end_ms = _last_30d_range_ms()
    dataset = {
        "exchange": "okx",
        "symbol": "BTC-USDT-SWAP",
        "interval": "1h",
        "start_ms": start_ms,
        "end_ms": end_ms,
    }

    workspaces_dir = os.getenv("APP_WORKSPACES_DIR") or os.getenv("WORKSPACES_DIR") or "/workspaces"

    report: dict[str, Any] = {
        "started_at": _utcnow().isoformat(),
        "api_base_url": api_base_url,
        "cases_total": len(cases),
        "llm": {
            "provider": os.getenv("LLM_PROVIDER") or "",
            "model": os.getenv("LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or "",
            "base_url": os.getenv("LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "",
        },
        "dataset": dataset,
        "results": [],
        "summary": {},
    }

    counts = {
        "conversion_succeeded": 0,
        "conversion_failed": 0,
        "backtest_succeeded": 0,
        "backtest_failed": 0,
    }
    failure_buckets: dict[str, int] = {}
    failures_out: list[dict[str, str]] = []

    for idx, case in enumerate(cases, start=1):
        t0 = time.time()
        row: dict[str, Any] = {
            "index": idx,
            "label": case.label,
            "url": case.url,
            "conversion": {},
            "backtest": {},
            "artifacts": {},
            "timing_s": {},
        }
        try:
            payload = _request_json(
                sess,
                "POST",
                f"{api_base_url}/api/strategies/import/tradingview",
                payload={"url": case.url, "strategy_name": f"[eval] {case.label[:80]}"},
                timeout_s=90,
            )
            job_id = payload["job"]["id"]
            strategy_id = payload["strategy"]["id"]
            version_id = payload["strategy_version"]["id"]
            row["conversion"].update(
                {
                    "job_id": job_id,
                    "strategy_id": strategy_id,
                    "version_id": version_id,
                    "status": "running",
                }
            )

            job = _wait_job(sess, api_base_url, job_id, timeout_s=args.job_timeout)
            row["conversion"]["status"] = job.get("status")
            row["conversion"]["error_message"] = job.get("error_message")

            validation = _read_validation_json(workspaces_dir, strategy_id, version_id)
            if validation:
                row["artifacts"]["pinescript_validation"] = {
                    "ok": validation.get("ok"),
                    "attempt": validation.get("attempt"),
                    "error": validation.get("error"),
                }

            if job.get("status") != "succeeded":
                counts["conversion_failed"] += 1
                msg = str(job.get("error_message") or "")
                bucket = _classify_failure(msg)
                failure_buckets[bucket] = failure_buckets.get(bucket, 0) + 1
                failures_out.append({"label": case.label, "url": case.url, "bucket": bucket})
                report["results"].append(row)
                continue

            if args.assert_strategy_py:
                files = _request_json(sess, "GET", f"{api_base_url}/api/strategies/{strategy_id}/files", timeout_s=60)
                items = files.get("files") or []
                strategy_py = next((f for f in items if f.get("name") == "strategy.py"), None)
                content = (strategy_py or {}).get("content") or ""
                if "def generate_signals" not in content:
                    raise RuntimeError("missing_generate_signals")

            counts["conversion_succeeded"] += 1

            if args.skip_backtest:
                report["results"].append(row)
                continue

            bt_payload = _request_json(
                sess,
                "POST",
                f"{api_base_url}/api/strategies/{strategy_id}/backtests",
                payload={"dataset": dataset, "params": {}},
                timeout_s=60,
            )
            bt_job_id = bt_payload["job"]["id"]
            run_id = bt_payload["backtest_run"]["id"]
            row["backtest"].update({"job_id": bt_job_id, "run_id": run_id, "status": "running"})

            bt_job = _wait_job(sess, api_base_url, bt_job_id, timeout_s=args.backtest_timeout)
            row["backtest"]["status"] = bt_job.get("status")
            row["backtest"]["error_message"] = bt_job.get("error_message")

            if bt_job.get("status") != "succeeded":
                counts["backtest_failed"] += 1
                msg = str(bt_job.get("error_message") or "")
                bucket = _classify_failure(msg)
                failure_buckets[bucket] = failure_buckets.get(bucket, 0) + 1
                failures_out.append({"label": case.label, "url": case.url, "bucket": bucket})
                report["results"].append(row)
                continue

            run = _wait_backtest_run(sess, api_base_url, run_id, timeout_s=args.backtest_timeout)
            row["backtest"]["run_status"] = run.get("status")
            row["backtest"]["metrics_keys"] = sorted(list((run.get("metrics") or {}).keys()))
            if run.get("status") == "succeeded":
                counts["backtest_succeeded"] += 1
            else:
                counts["backtest_failed"] += 1
                failure_buckets["backtest_run_failed"] = failure_buckets.get("backtest_run_failed", 0) + 1
                failures_out.append({"label": case.label, "url": case.url, "bucket": "backtest_run_failed"})

            report["results"].append(row)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            row["conversion"]["status"] = row["conversion"].get("status") or "error"
            row["conversion"]["error_message"] = msg
            counts["conversion_failed"] += 1
            bucket = _classify_failure(msg)
            failure_buckets[bucket] = failure_buckets.get(bucket, 0) + 1
            failures_out.append({"label": case.label, "url": case.url, "bucket": bucket})
            report["results"].append(row)
        finally:
            row["timing_s"]["total"] = round(time.time() - t0, 2)

    report["finished_at"] = _utcnow().isoformat()
    report["summary"] = {
        **counts,
        "conversion_rate": (counts["conversion_succeeded"] / max(1, len(cases))),
        "backtest_rate": (counts["backtest_succeeded"] / max(1, len(cases))),
        "failure_buckets": dict(sorted(failure_buckets.items(), key=lambda kv: (-kv[1], kv[0]))),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    with open(args.out_failures, "w", encoding="utf-8") as f:
        json.dump({"generated_at": _utcnow().isoformat(), "failures": failures_out}, f, ensure_ascii=False, indent=2)

    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
