# Trendilo-inspired research candidate — 8 November 2026

**Research-only. No real orders, credentials, account connections, wallet actions, or updates to the running paper bot.**

This is an independent, simplified Trendilo-style hypothesis, not the actual original indicator or a reproduction of any paid/proprietary strategy. Public completed Binance BTC/USDT spot and Hyperliquid BTC perpetual 1-hour candles (up to 4,000 each) are evaluated, with no live trading.

- Oscillator: ALMA 20 of completed one-bar percentage returns.
- Bands: prior 20 oscillator readings' mean ± 1.5 standard deviations.
- Long entry on upward upper-band crossing with positive momentum and 20/50-bar trend confirmation; exit on momentum turn or lower-band crossing.
- Baseline: independent 5/20 SMA crossover with the same simulated execution costs.
- Risk: virtual $10,000 per independent test, $200 maximum buy budget, stop bounded by 2% or 2×ATR, and a 1%-of-start-of-day-equity simulated daily loss pause. This is not a guarantee against gap losses.
- Signal at completed candle close; hypothetical fill at next candle open; entry-bar stops allowed. 0.1% fees and 0.05% slippage each side (doubled in a stress run).
- Fixed chronological 70/30 train/holdout; no fitting to the holdout. No risk-matched production comparison.
- Output: generated `trendilo-results/REPORT.md` as a GitHub Actions artifact; not committed to `main`, `paper-results`, or any ledger.
- No funding rates, spreads beyond assumptions, market depth, order rejections, liquidation, actual stops or guaranteed fills.

Use `python -m unittest discover -s tests -v` for offline tests, then `python trendilo_lab.py` to fetch public research data. The latter requires network access and may fail closed when a market is unavailable; no report should be interpreted as an all-clear for real-money trading.

4,000 hours (~167 days) still cannot establish a durable edge across market regimes. A zero-trade or positive short-window result is not proof. Compare after costs; then use substantially longer untouched samples and sustained forward testing before even discussing real trades.

This feature branch is intentionally separate from the running virtual ledger. Do not merge any trading logic into the live paper simulator without further review.
