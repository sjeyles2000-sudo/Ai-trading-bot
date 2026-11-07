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


## Proposed scheduled, persistent demo mode (PR #2)

After this change is reviewed and merged, GitHub Actions can run once per hour
(17 minutes past the hour, UTC). GitHub schedules are approximate and may be delayed
or skipped. No computer, Binance account, Hyperliquid account, wallet, API key,
or hosting subscription is required.

Run code: `python demo_runner.py` (virtual results in `ledger/` locally).
GitHub workflow checks out a separate `paper-results` branch and saves virtual
account state, virtual transactions (`ledger/trades.csv`), hourly account snapshots
(`ledger/equity.csv`), and a human-readable `ledger/REPORT.md` there.
See the `paper-results` branch after the FIRST successful scheduled or manually
dispatched run. The initial results branch has no ledger until then.

The virtual starting balance is **$10,000 USD per exchange**, independent for each
exchange. Positions are long-only and simulation-only. Each run reads **public**
exchange data; no authenticated or trade endpoints exist. Only completed hourly
candles are processed. A repeated candle is not traded twice. On startup, the
program begins with the latest completed candle; it never credits historical
backtest profits to the new paper account. If saved position data is corrupt, too
old for the available candle history, or either exchange is unavailable, that
run fails and does not push any results. It does not automatically reset virtual
positions to conceal data gaps. The daily loss limit uses UTC calendar days.

This is an **estimated-fill educational simulation**, not exchange-native paper
trading or a realistic execution emulator. Funding, leverage, liquidation,
order-book depth, and strategy performance require further work. The recurring
workflow is intentionally restricted to the default `main` branch. The test
workflow uses mocked exchange responses and never places orders.

**No live order functionality, trading credentials, or exchange write
permissions are included.** Do not treat virtual performance as investment advice.


## Read-only FOMO, wallet, scalping and meme-coin research radar (proposed PR #3)

`python research_radar.py` gathers **completed five-minute public candles**
for BTC on Binance spot and Hyperliquid perpetuals. It labels short-term
price/volume patterns as `FOMO_RISK`, `BULLISH_WATCH`, `BEARISH_WATCH`, or
`NO_SIGNAL`. These are **research flags, not automatic orders, copy-trading,
or proven profitable signals**. A FOMO flag is a warning against chasing spikes.

The research scanner also uses DEX Screener's **recently profiled tokens**
and reported pair liquidity, age, and volume to build a watchlist.
**Recently profiled is NOT the same as newly launched**, and paid promotions may
influence what appears. No meme coin is automatically bought or assigned
position size. Basic liquidity/age/volume thresholds do **not** establish
whether a token is safe. Before any discretionary investment, investigate
contract privileges, honeypots, ownership concentration, distribution,
liquidity locks, fees, slippage, manipulation, and legal restrictions.

For public Hyperliquid wallet activity, place up to 10 **manually verified**
public 42-character hexadecimal wallet addresses in
`config/wallet_watchlist.json` on the `research-results` branch as a JSON
array of strings. Empty or absent watchlists are allowed. No wallet addresses
are presumed to be top-performing. Reported wallet fills are not a complete
proof of profit or skill; there is **no copy-trade execution**.

After merging the radar workflow into `main`, scheduled GitHub Actions attempts
an hourly scan at minute 37 UTC. Reports go to
`research-results/research/RADAR.md`. Runs can be delayed, fail or be skipped;
failed feeds are reported without fabricated signals. A scheduled scan is not
real-time scalping infrastructure. No Telegram connection or push alerts are
configured yet, and trading decisions remain manual.
