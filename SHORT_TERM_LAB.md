# Short-term paper strategy lab (research only)

This is a **standalone, read-only historical BTC backtest** for Binance BTC/USDT spot and Hyperliquid BTC perpetual. It is separate from `demo_runner.py`, the scheduled `paper-results` state, the public monitor, wallet research, and any future real-money execution.

## Compare two fixed strategies

- **5-minute scalping candidate:** EMA8 crosses EMA21 upward on a *completed* 5-minute candle and reported volume is at least 1.1 times the mean volume of the preceding 20 completed candles. Exit when EMA8 falls below EMA21 or close falls below EMA8.
- **15-minute candlestick candidate:** Bullish engulfing body after a bearish body, with the new completed close above EMA20. Exit on bearish engulfing or close below EMA20.

Both use long-only entries. Each signal is computed after a candle closes, and orders are **hypothetical fills at the next candle open**, never real exchange orders.

## Controls and assumptions

- Each market / strategy / time split starts with an independent $10,000 **virtual** account.
- Maximum virtual allocation per entry is **2%**, without leverage.
- Hypothetical per-side costs are **0.10% fees plus 0.05% slippage** (assumed, not a verified exchange schedule).
- Stop level: **0.5%** on 5-minute and **1%** on 15-minute entries. Price gaps and same-bar stops are simulated conservatively, not guaranteed fills.
- A **1% daily marked-equity drawdown** pauses new entries and flags an open position for exit on the next candle. Losses can exceed the threshold.
- Fixed chronological 70% training / 30% untouched holdout: the holdout starts with new virtual cash; prior candles are permitted only for indicator warmup.
- A failed, missing or stale feed prevents a report from being written. The bot does not claim success on incomplete data.

## Run and inspect

```bash
python -m unittest discover -s tests -v
python short_term_lab.py
```

The report is written to `backtest-results/short-term.md` **locally only**, not committed to the real paper-trading ledger. Alternatively, run **Short-term strategy research (read-only)** from GitHub Actions or inspect its branch-push run and download the `short-term-paper-research` artifact.

The report includes the strategy decision tree, simulated return, drawdown, closed trades, win rate, profit factor, and critical limitations. The dashboard and trading logic on `main` are unchanged until a reviewed merge, and even a merge **does not enable live orders or replace the hourly strategy**.

## Interpretation

A successful CI run proves the code completed and tested safely; it does **not** prove market profitability. The 1,000-candle request spans only about 3.5 days at 5 minutes or 10.4 days at 15 minutes. The four trials share BTC exposure and are not independent market regimes. Results omit funding, real order-book execution, exchange latency and market impact. Apparent wins from very few trades are not evidence of a durable edge.

**Do not allocate real capital based on this report.** Extend the dataset, include sideways/trending/stressed periods, model funding and venue-specific costs, then run longer forward paper tests with monitored risk limits.
