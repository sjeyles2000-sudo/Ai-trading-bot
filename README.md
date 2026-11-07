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


## Public leaderboard research (proposed PR #5)

`python wallet_leaderboard.py` downloads Hyperliquid's public leaderboard
**once per run** and selects at most five accounts for manual study.
Selection requires positive reported daily, weekly and monthly PnL, at least
$20k account value, $100k reported monthly traded volume, and a positive but
not extreme reported monthly ROI (0–500%). Ranking is by reported monthly PnL.
These metrics can be distorted by leverage, deposits, withdrawal effects,
survivorship bias, attribution and missing history; a top trader is **not**
necessarily worth copying. Reported ROI is not audited performance.

The scanner then requests recent **public fills** for the shortlisted wallet
addresses. It does not connect to those wallets, manage balances or submit
trades. It saves a daily `research/WALLETS.md` report to the existing
`research-results` branch when the scheduled GitHub Action becomes active
on main. Its schedule is daily at 03:43 UTC; schedules can be delayed or
skipped. The leaderboard JSON is a large public feed and may fail, change
shape or become unavailable. A failed report does not turn into a signal.

This is a **read-only wallet research feature**, not automated copy-trading,
meme coin orders, real scalping infrastructure, or a profit guarantee.
Public data sources: `stats-data.hyperliquid.xyz/Mainnet/leaderboard` and
Hyperliquid's public `/info` userFills endpoint.


## Offline backtesting and performance reports (proposed PR #7)

Run `python run_backtest.py` for **historical research only**. It requests the
same completed 1h Binance BTC/USDT spot and Hyperliquid BTC perpetual candles
used by `bot.py`. It creates standalone `backtest-results/binance.md` and
`backtest-results/hyperliquid.md`; it does **not** access `ledger/`, update
virtual accounts, or submit orders. Reports are generated only after both
market feeds have passed validation and completed the tests.

The baseline is a **fixed** long-only 5/20 moving-average crossover. Signals
use completed candles and hypothetical next-bar open fills to avoid direct
lookahead. The research simulation caps each buy at 2% virtual notional,
uses a price stop, and assumes fees and slippage. The persistent paper
trader has separate daily loss controls and is NOT replaced by this code.

Each report distinguishes a chronological 70% training segment from a 30%
holdout segment (with a price-history warmup). Returns, max drawdown, closed
trades, win rate and profit factor are calculated from the simulation.
Very few trades or losses produce **N/A**, not an inflated accuracy claim.
The training and holdout results begin with independent virtual balances;
neither includes real funding, actual order-book depth, spreads, leverage,
liquidation, market impact, or true exchange fills.

Short one-hour candle samples are insufficient to validate profitability.
Do not tune strategies to the holdout set then present its return as
unbiased evidence. For robust testing, use longer, segmented market
histories with different regimes before considering any real capital.

No external TA-Lib, VectorBT, QuantStats, or exchange credentials are
needed. Run offline checks with
`python -m unittest discover -s tests -v`.
