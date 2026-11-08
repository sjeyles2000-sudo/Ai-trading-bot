# Bot-profitability research: X claims, independently checked snapshots and practical tests
_Researched 8 November 2026. Information only, not investment advice. **No real trading authorised.**_

## What is verifiable
In social media posts on X, a PnL screenshot, high win rate, or advertised APR is
**not proof** of audited net profits. Many X posts were not independently retrievable
from public search, so this document **does not attribute unverified returns to
specific X accounts**. Stronger evidence is publicly trackable venue history
plus fees, realized/unrealized positions, deposits/withdrawals, and drawdown.

Third-party snapshot of public Hyperliquid vault records **as of 7 Nov 2026**:
https://getbotornot.com/proven-returns/
- Systemic Strategies L/S Grids (self-described grid): about **+$1.20m 30d**,
  **+$2.59m all time**, roughly **$10.96m deposits**. Publicly tracked
  *vault*, not a replicable bot blueprint; unknown private parameters.
- Growi HF (self-described quantitative): about **-$134k 30d**,
  **+$2.81m all time**, roughly **$12.50m deposits**.
- drkmttr (self-described market making): about **-$2.76m 30d**,
  **+$3.64m all time**, roughly **$7.15m deposits**.
- Probot 5/9/12 (self-described bot): about **-$7.5k 30d** and
  **-$2.4k all time**. This is a reminder that a name containing
  'bot' doesn't imply an edge.
Numbers are third-party calculations from on-chain records. They do not prove
every trade was automated; dollar PnL alone does not equal individual investor
return, and timing, deposits, leader fee cuts and exposure change comparisons.

Published forward **dry-run**, not live orders: Perpex Slingshot reports
**+14.24% since Aug 21**, but **-6.86% last 30 days** as of research date.
A win rate of 92% obscures that average win is only 0.13× average loss; full
equity and drawdown matter more than wins alone.
Source: https://perpex.co/algo-bots

Pionex expressly distinguishes grid profit from **total profit including
unrealized losses**, and states that positive grid profit can coexist with
overall losses: https://www.pionex.com/blog/knowledge-base/what-are-grid-profit-and-unrealized-profit/

## Strategy ideas worth independently testing
1. **Trend vs chop regime selection**: completed hourly BTC trend-following
   with volatility and liquidity gates; compare against buy-and-hold/cash
   and ordinary SMA.
2. **Mean-reversion / VWAP pullbacks**: only in sufficiently liquid markets,
   with strict stop-and-time exits, no averaging down; test across both
   trending and sideways regimes.
3. **Inventory-controlled market making**: Hummingbot documents spread
   management, quoting and inventory skew. This requires real order-book
   and queue simulation, so do **not** port directly into a candle-based
   backtest. https://hummingbot.org/strategies/v1-strategies/strategy-configs/inventory-skew/
4. **Grid with a strict trend/range filter**: compare full mark-to-market
   equity after fees rather than the 'grid profit' marketing metric.
5. **Public-wallet and cross-market mispricing research**: research only.
   Polymarket arbitrage and copy-trading claims depend heavily on simultaneous
   fills, race latency, fee schedules, settlement and regional eligibility;
   do not infer a risk-free edge from a hypothetical two-leg quote.

## Evidence standard for our bot
- Strict chronological out-of-sample testing on separated market regimes;
  no tuning on the holdout. Prefer several years of data if possible.
- Costs measured from actual fee schedules where known, plus conservative
  spread, slippage, funding, failed fills, latency and gap scenarios.
- Next-bar execution for bar-close strategies, lookahead-bias checks,
  realistic stops and position valuation; avoid cherry-picked symbols.
- Report **net full-equity return, max drawdown, losses, profit factor,
  exposures, number of closed trades**, and compare to BTC buy-and-hold.
- Reject strategies with only a handful of trades, positive in-sample only,
  negative cost-stress results or failure in a sustained paper-forward period.
- For Binance Australia, keep research on spot unless eligibility changes.
  Hyperliquid perpetuals: simulate only, no actual leverage or order keys.
- Keep Binance/Hyperliquid running paper ledger completely unchanged.
- Do not connect exchange private credentials to any cloud provider or repository.
- A public ledger snapshot is evidence of historic results **not proof of
  future profitability**; no 'guaranteed profitable bot' exists.

## Existing repo research
Trendilo-inspired vs 5/20 SMA, separate draft PR #16:
https://github.com/sjeyles2000-sudo/Ai-trading-bot/pull/16
The old 600-hour test was much too short. The updated code requests 4,000
completed 1-hour candles per market with bounded Binance paging and
fail-closed checks for gaps, then generates a new isolated report. The
4,000-hour historical experiment **passed its software checks** but found
**negative out-of-sample returns** after assumed trading costs:
- Binance Trendilo-inspired: -0.0110%, 11 closed virtual trades;
  double-cost stress: -0.0809%.
- Hyperliquid Trendilo-inspired: -0.0174%, 11 closed virtual trades;
  double-cost stress: -0.0821%.
- Both beat the similarly tested 5/20 SMA baseline in this window, but
  neither passed a positive-return holdout test.
Full report: https://github.com/sjeyles2000-sudo/Ai-trading-bot/actions/runs/42432655299

**Do not deploy this candidate for live trading.**

Read-only server draft PR #18:
https://github.com/sjeyles2000-sudo/Ai-trading-bot/pull/18
Railway service and persistent volume are staged, not activated.
