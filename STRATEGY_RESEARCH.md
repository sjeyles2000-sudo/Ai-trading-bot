# Breakout versus pullback BTC research (8 November 2026)

This separate draft branch adds `strategy_lab.py` and offline regression tests.
It **does not change** the running hourly demo simulator, persistent paper
ledger, Railway staged server, or account exchange permissions. There is
no authentication, no private API keys, no orders or wallet control.

The experiment fetches 4,000 **completed one-hour** BTC candles from each
venue using public Binance spot and Hyperliquid perpetual market-data APIs,
checks for gaps and stale prices, and tests:
- **Breakout:** Long entry after close above the prior 20-hour high,
  conditioned on the close above the 200-hour SMA and SMA50 above SMA200.
  Exit on close below SMA50, filled at next bar open.
- **Pullback:** Long entry only in a bullish SMA50>SMA200 regime when
  close is more than 1% below SMA20 and RSI(2) is below 20. Exit on recovery
  to SMA20 or a trend break below SMA200, filled next open.
- **Baseline:** 5/20-hour SMA bullish crossover, exit below SMA20.

All three use identical virtual starting capital and 2% maximum equity
allocation per entry, 2.5% price-based stop, 1% virtual UTC daily loss
pause, and hypothetical 0.1% fee + 0.05% slippage **per side**. Stress
test doubles both costs. Same-bar stops can trigger pessimistically.
Independent chronological 70/30 train/holdout accounts reset balances at
the split. The holdout is not used to tune parameters. Benchmark includes
2%-allocation BTC buy/hold and 100% BTC buy/hold (different exposure).

IMPORTANT LIMITATIONS:
- One 167-day BTC sample cannot establish reliable profitability, and
  strategy choices remain illustrative hypotheses. No multiple-regime
  walk-forward or out-of-sample repeated validation yet.
- Hourly bar data cannot model order-book queue, funding payments, adverse
  selection, actual spreads, market impact, partial fills, outages or
  funding/liquidations for Hyperliquid perpetuals.
- The algorithm uses simplified 2-bar RSI, not a full Wilder-smoothed RSI.
- A simulated stop can fill worse than its threshold on gaps.
- Daily-loss control restricts new entries and requests next-open exit,
  not guaranteed protection from gaps, market moves or overnight losses.
- Separate simulated long-only perpetual exposure without funding is NOT
  a full-fidelity Hyperliquid execution model.
- Full 100% buy-and-hold benchmark is not risk matched to 2% allocation.
- Positive results would only justify more independent research and forward
  paper trading, not live trading approval.

Read the GitHub Actions artifact `breakout-pullback-research` for full
results, including isolated holdout and doubled-cost stress. Refuse to
promote any candidate without positive net holdout/stress results,
adequate number of trades, acceptable drawdowns and sustained forward
paper results. This branch is for research, not trading.
