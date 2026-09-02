---
name: analyze
description: Read the current strategy and report what it does, where its risk sits, and what is worth changing next. Use before editing an unfamiliar strategy, or when a backtest result needs explaining.
---

# Analyze the current strategy

Read `strategy.py` in full before saying anything about it. Partial reads produce
confident wrong answers about strategies, because the risk usually lives in the
part that looks like boilerplate.

Report four things, briefly:

1. **Entry and exit** — what conditions open a position, what closes it, and on
   which bar each decision is made. Name the indicator and its lookback.
2. **Position sizing** — fixed size, volatility-scaled, or target weights, and
   whether the strategy can end up leveraged.
3. **Where it breaks** — the market regime this logic is worst at. A trend
   follower in a range, a mean reverter in a trend, anything with a hard-coded
   threshold that assumes a price level or a volatility level.
4. **The next change worth testing** — one change, with the reason you expect it
   to move the score, not a list of everything adjustable.

If a recent `backtest` run is available, tie the analysis to its numbers: say
which part of the logic produced the drawdown or the flat stretch, rather than
restating the metrics.

## Lookahead

While reading, check for lookahead explicitly. Any use of the current bar's close
to decide the current bar's position, any `shift(-n)`, any indicator computed
over the whole series and then indexed at `i`, is a bug that makes every metric
meaningless. Report it first if you find it.
