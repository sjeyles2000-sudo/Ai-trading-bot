# Momentum breakout research — paper-only prototype

This is an **original, simplified crypto hypothesis** prompted by Kristjan Kullamägi (Qullamaggie)'s free material. It is **not** a faithful reproduction of his discretionary US-stock methodology and is not an indication of expected profits.

Primary references:
- https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/
- https://qullamaggie.com/faq/

## What has been implemented

- `qulla_breakout_lab.py` is a pure Python historical simulation module using **pre-supplied** daily OHLCV data. It does not fetch prices or connect to any exchange.
- An exploratory close-confirmed breakout above the previous ten-day high after a prior narrow trading range, with a rising 20-day average and higher-than-normal volume.
- Entry only at the next bar's opening price, not on the same close that generated the signal.
- Maximum 2% **virtual notional** allocation; extra 0.25% theoretical equity-at-risk budget based on initial stop distance. Fees, slippage and gap-risk can make actual hypothetical loss exceed the estimate.
- A protective stop based on prior ten-day lows; closing-average exit is evaluated from **completed prior bars**, never the current bar's close. For daily candles, a 1% marked-equity loss triggers a one-bar cooldown for new entries on the next day (not a true intraday risk circuit breaker).
- Separate 70/30 chronological training/holdout simulations, with independent virtual starting cash, plus doubled-cost holdout stress checks.
- Offline synthetic regression tests in `tests/test_qulla_breakout_lab.py`.

## Deliberate limitations

- The prototype does NOT trade, write ledgers, create ongoing alerts, or collect historical prices. The only tests provided are synthetic, not empirical profitable results.
- The daily breakout model is not 5-minute scalping. Qullamaggie's episodic pivots, cash-market opening auction and stock-leadership scans cannot simply be substituted with BTC.
- The code assumes clean consecutive 24-hour bars, ignores funding, market impact, true bid/ask spread, exchange limits, portfolio correlations and liquidation.
- End-of-window open positions are only marked to market; no extra final sale charge is added to those open positions.
- The proposed 12% compression threshold and 1.2x volume threshold are arbitrary **pre-specified research parameters**, not official Qullamaggie rules.
- Backtests are not independently validated by published return histories. No exchange data or market regime coverage has yet been tested.

## Running offline

```bash
python -m unittest discover -s tests -v
```

To compare actual historical crypto prices later, obtain a properly licensed, point-in-time daily OHLCV dataset and explicitly validate its UTC daily boundaries, freshness and exchange-specific costs. No real order keys are required.

## Decision gate

Do not merge this model into `bot.py` or `demo_runner.py` until a genuinely independent dataset supports repeatable net-of-cost results over different regimes and a sustained forward paper trial. No real money should be connected by this research PR.

## Verified first public-market run (7 November 2026)

GitHub Actions research run: https://github.com/sjeyles2000-sudo/Ai-trading-bot/actions/runs/42371009704

- 50 offline repository regression tests passed.
- Read-only public feeds delivered 900 consecutive completed daily candles for each of Binance BTCUSDT/ETHUSDT spot and Hyperliquid BTC/ETH perpetuals.
- Data window: 2024-05-21 to 2026-11-06 (UTC).
- **No breakout trades occurred**: both train and holdout portfolio returns are 0.000%, closed holdout trades = 0, and max holdout drawdown = 0.000% in all four cases.
- A 2%-notional passive BTC/ETH position over the holdout returned approximately +0.156%, +0.121%, +0.157%, and +0.121% respectively after assumed fees and slippage. This is not a risk-matched benchmark; perpetual funding is omitted.
- The tested breakout rules are **unproven**: zero trades do not demonstrate safety or profitability. Do **not** optimize these exact parameters on the already-observed holdout and call the result unbiased.
- Any next hypothesis should be specified in advance and evaluated on a *new, untouched later* period, with realistic venue execution costs.

The empirical report is uploaded as a temporary GitHub Actions artifact, not written to the existing persistent paper ledger. GitHub Actions schedules and external public feeds can fail or become unavailable.
