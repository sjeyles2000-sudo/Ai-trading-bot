# Fixed price action experiment (research only)

Run `python compare_price_action.py` to generate an independent comparison report for public completed **1h** BTC candles on Binance spot and Hyperliquid perpetual. No keys, orders, broker connection, persistent positions, or changes to the live paper ledger. The hourly production simulator remains unchanged.

This first experiment evaluates a deterministic **long-only breakout/retest**:
- Resistance = highest high in twenty candles preceding the breakout.
- Breakout candle closes above resistance, opens at/below it, and its close is above the previous 20-candle SMA.
- Next candle touches resistance and closes green above it; only then can an entry be made at the *following* candle's open.
- Stop is below the retest low/resistance by 0.1%; skip entries if stop distance exceeds 2% of entry. Set target at two times the stop distance. Conservative stop-first exit when stop and target are both in one candle.
- Simulated trade notional <=2% of a separate $10,000 virtual account; capped by 0.5% initial account risk at the specified stop, excluding adverse gap risk.
- Include assumed 0.1% fees and 0.05% slippage per side, reject missing data, and independently report train and chronological holdout.
- **Do not treat win rate or profit factor with zero or few closes as evidence of success.**

The baseline existing SMA 5/20 strategy and new rules are research-only comparisons. Only 120 recent hourly candles are currently available, so neither covers a robust range of volatility regimes. No margin, funding, spread, latency, liquidations, or actual liquidity model is implemented. Live markets and real-money order execution stay disabled. 5m/15m support is a *future* experiment, not claimed here.
