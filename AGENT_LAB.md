# Five-role agent paper research lab

This isolated proof of concept adapts the *specialised-agent workflow* concept from social-media trading discussions. It is **not** a reproduction of any proprietary trading bot, and it does not use Grok, ChatGPT APIs, model-generated orders or new paid subscriptions. The five 'agents' are deterministic, separately testable Python roles.

- Market scanner — observes completed 1h BTC candles and fixed SMA 5/20.
- Strategy agent — BUY_WATCH, SELL_WATCH or HOLD from an unchanged crossover baseline.
- Risk manager — 2% maximum virtual position allocation, 1% daily virtual loss pause and a 5% previous-candle-range veto.
- Paper trader — simulated next-open entry/exit, 2% price-based stop, conservative intrabar stop treatment, assumed fees (0.1% each side) and slippage (0.05% each side).
- Performance analyst — hypothetical after-assumed-fee account return, closed-bar max drawdown, fees, virtual transactions and a win rate only when there are closed positions.

## Run

Requires Python 3.10+, standard library only, from repository root:

```bash
python -m unittest discover -s tests -v
python agent_lab.py
```

The lab uses the **existing unauthenticated public** Binance BTC/USDT spot and Hyperliquid BTC perpetual hourly price readers from `bot.py`. Output is JSON to stdout only. It produces no partial results if either market fails, and does not create or modify any financial ledger. The tests use synthetic data and do not call the network.

## Separation and safety

This PR **does not modify** `bot.py`, `demo_runner.py`, recurring workflows, virtual accounts, `paper-results`, secret configuration, notifications, wallets, exchange keys or trading permissions. Nothing is deployed and it does not execute on a schedule. `LIVE_ORDERS_ENABLED = False` is hardcoded and `place_live_order()` always raises. Do not interpret it as an executable real-money trading service.

This historical toy experiment uses roughly 120 one-hour candles (fewer actual trades), so profitability is **not** demonstrated. The fixed SMA strategy is not an AI market prediction. No shared capital/risk limit across venues, funding, liquidation, latency, spreads, partial fills or order-book depth are simulated. Hourly drawdown misses intrabar peaks. Even next-open simulated fills can be unrealistic. Negative performance, no trades, or a positive short run do **not** establish an edge.

For later evaluation: run thousands of historical bars, precommit to parameters, use untouched chronological holdout regimes, report fee/slippage stress, compare to a position-size-matched passive BTC benchmark, and separately review the existing concurrent strategy PRs. Real orders stay disabled pending independent security, suitability and operating reviews and your explicit separate approval.
