#!/usr/bin/env python3
"""Backfill `Dataset.symbol` onto the canonical notation.

Historically the AI requirement summary could produce `BTC/USDT`, which was
stored verbatim and later sent to OKX as an instId (error 51001). Dataset symbols
are now canonicalised at the API boundary; this rewrites rows created before
that, so old rows stop carrying an exchange-native slash form.

Canonical notation is `BASE-QUOTE[-SWAP]` (`BTC-USDT`, `BTC-USDT-SWAP`), US
stocks are the bare ticker (`BRK-B`).

Dry run by default; pass `--apply` to commit.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../packages/control_plane")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../packages/data")))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Dataset
from data.instruments import InvalidInstrument, normalize_symbol
from app.settings import settings


def backfill(apply: bool) -> int:
    engine = create_db_engine(settings.db_url)
    changed = 0
    skipped = 0

    with session_scope(create_session_factory(engine)) as db:
        for dataset in db.query(Dataset).all():
            raw = (dataset.symbol or "").strip()
            try:
                canonical = normalize_symbol(raw, exchange=dataset.exchange)
            except InvalidInstrument:
                print(f"SKIP  {dataset.id}  exchange={dataset.exchange}  symbol={raw!r}")
                skipped += 1
                continue
            if canonical == raw:
                continue
            print(f"FIX   {dataset.id}  {dataset.exchange}  {raw!r} -> {canonical!r}")
            dataset.symbol = canonical
            changed += 1

        if not apply:
            # Roll back the pending updates so a dry run has no side effects.
            db.rollback()

    verb = "changed" if apply else "would change"
    print(f"\n{changed} dataset(s) {verb}; {skipped} skipped (unparseable).")
    if not apply and changed:
        print("Re-run with --apply to commit.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    args = parser.parse_args()
    return backfill(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
