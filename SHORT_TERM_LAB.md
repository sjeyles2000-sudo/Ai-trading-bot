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

The report includes the strategy decision tree, simulated return, drawdown, closed trades, win rate, profit factor, doubled-fee/slippage stress testing and critical limitations. The dashboard and trading logic on `main` are unchanged until a reviewed merge, and even a merge **does not enable live orders or replace the hourly strategy**.

## Holdout stability upgrade

The report now subdivides the **same untouched final 30% holdout** into
three consecutive, non-overlapping windows, each starting with an independent
$10,000 virtual account and using earlier bars only for indicator warm-up.
The table shows return after assumed costs, drawdown and closed trade count for
each window. The full holdout figure remains the primary comparison and the
three window returns are **not additive**.

For insufficient data (fewer than 270 holdout bars), the per-window table
reports **N/A** instead of pretending to validate stability. These are
diagnostics on the same BTC sample, not independent out-of-sample datasets
or proof of profitable future trading. Do not pick the best-performing
window or retune rules after inspecting these results.

## Rule-based benchmarking, not AI price guesses

The holdout report compares each fixed, rule-based candidate against a
**passive BTC reference** over exactly the same holdout interval. The
reference hypothetically allocates only 2% of a fresh $10,000 virtual
account to BTC at the first candle's open, then sells at the final close.
Both sides pay the same assumed fee and slippage as the strategy.
The comparison reports the BTC price change, reference portfolio return,
active strategy portfolio return and the difference in percentage points.

**Important limitations:** the reference stays exposed for the whole interval,
while each short-term strategy trades intermittently and uses a stop; their
risks are not matched. Reference results assume a final sale whereas
strategy equity can still contain an open marked-to-market position. BTC
perpetual funding and real execution quality are omitted. Beating a losing
reference, especially with zero strategy trades, is **not proof** of a profitable
quantitative edge. Do not use this diagnostic to pick the best variant on
the same holdout sample.

## Interpretation

A successful CI run proves the code completed and tested safely; it does **not** prove market profitability. The 4,000-candle request spans only about 14 days at 5 minutes or 42 days at 15 minutes. Binance history is retrieved in bounded pages; Hyperliquid uses its latest available public candles. These are still too short to establish robust profitability. The four trials share BTC exposure and are not independent market regimes. Results omit funding, real order-book execution, exchange latency and market impact. Apparent wins from very few trades are not evidence of a durable edge.

**Latest read-only test (7 November 2026):** the new comparison passed all 49 repository checks and fetched 4,000 completed candles for each of the four cases. Every out-of-sample holdout return was negative after assumed transaction costs; the doubled-cost stress case was worse for all four. The full report is an artifact of the GitHub Actions workflow, not a profit guarantee.

**Do not allocate real capital based on this report.** Extend the dataset further with separate training and validation periods, include sideways/trending/stressed regimes, model funding and venue-specific costs, then run longer forward paper tests with monitored risk limits.


## Experimental one-minute breakout comparison (9 November 2026)

A new **separate, research-only** module `minute_breakout_lab.py` investigates
a documented breakout hypothesis motivated by the MambaFx scalping discussion,
**not** a verified reproduction of the presenter's actual private trade rules.
It compares 1-minute close above the preceding ten 1-minute highs **with**
versus **without** a filter based on completed five-minute candles and EMA50.
Virtual entries use the following 1-minute open, with local-low price stops,
a 3R target hypothesis, stop-first ambiguous bars, maximum 30-minute hold,
2% virtual notional, 0.1% modeled fees plus 0.05% slippage per side, and
doubled cost stress. Research uses up to 4,000 recently completed 1-minute BTC
candles separately for Binance spot and Hyperliquid perpetual; the short
~2.8-day history and shared BTC price risk cannot validate profitability.
Real spreads, funding, queue position, market impact and liquidation are
not modeled. Indicators are *not* trained or tuned on the holdout.

Offline tests include no future lookahead, conservative same-bar stop ordering,
zero-trade reporting, invalid candle rejection and fail-closed missing-feed
behavior. The new `minute-breakout-research.yml` workflow runs on the
research branch only and may produce an artifact called
`minute-breakout-paper-research`. **No strategy promotion and no live orders.**
The original persistent scheduled `main` trader and all virtual ledger files
remain unchanged. Check the actual workflow results before claiming any gains.
