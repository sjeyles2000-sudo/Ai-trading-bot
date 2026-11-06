# AI Trading Bot — read-only paper simulation

This project retrieves **public completed hourly Bitcoin candles** from Binance BTC/USDT spot and Hyperliquid BTC perpetuals. It replays historical simulated orders with **virtual cash only**. It never authenticates to an account, signs a trade, or calls an order endpoint. **Real trading is not supported.**

## Running locally

Requires Python 3.10+ only (standard library):

```bash
python bot.py
python -m unittest discover -s tests -v
```

Each run fetches approximately 120 historical one-hour candles for each market and replays a moving-average crossover strategy. Results are historical *hypothetical* transactions, **not continuously running live paper trading**. Balances reset on every run. If one market cannot provide valid, fresh, complete candles (including due to geographic restrictions), it is skipped; the program exits nonzero when either market fails. No API keys or exchange accounts are needed.

## Risk assumptions and limitations

Each market separately starts with a $10,000 *virtual* balance (not shared funds). The strategy uses 5/20-period moving averages with long-only entries, 2% max notional virtual account allocation per entry, 2% virtual price-based stop loss, and 1% UTC calendar-day virtual loss pause. It assumes hypothetical 0.1% per-side transaction fees and 0.05% per-side slippage. The simulated stop may fill below its stop threshold on gaps. Historical-candle calculations are simplified and cannot reliably model real-world latency, order-book liquidity, funding, leverage, liquidation, or execution quality. Binance spot BTC and Hyperliquid BTC perpetuals are different instruments. Backtesting does not demonstrate future profitability.

Data sources: [Binance spot market-data endpoint](https://developers.binance.com/en/docs/binance-spot-api-docs/rest-api/market-data-endpoints) and [Hyperliquid /info candleSnapshot](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).
