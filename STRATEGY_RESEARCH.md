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

## First actual historical results (GitHub Actions, 8 Nov 2026)

Source: https://github.com/sjeyles2000-sudo/Ai-trading-bot/actions/runs/42433072522

| Venue | Candidate | Train | Untouched holdout | Doubled-cost holdout | Closed holdout trades |
|---|---|---:|---:|---:|---:|
| Binance BTC spot | Breakout | +0.092% | **-0.125%** | -0.178% | 9 |
| Binance BTC spot | Pullback | +0.028% | **-0.020%** | -0.050% | 5 |
| Binance BTC spot | SMA | -0.173% | -0.302% | -0.521% | 37 |
| Hyperliquid BTC perpetual | Breakout | +0.104% | **-0.125%** | -0.179% | 9 |
| Hyperliquid BTC perpetual | Pullback | +0.044% | **-0.022%** | -0.052% | 5 |
| Hyperliquid BTC perpetual | SMA | -0.162% | -0.319% | -0.543% | 38 |

**Decision:** Neither candidate passed the positive holdout and double-cost
stress requirements. Pullback lost less than breakout but only generated
five closed test trades per venue. Do **not** merge any strategy into the
running paper trader or deploy it live based on these findings. Continue
with additional non-overlapping market regimes, longer samples, proper
funding-aware perpetual testing and forward paper trading. The apparent
similarity between Binance and Hyperliquid results reflects highly
correlated BTC prices, not two independent strategy validations.

## Second round: additional fixed rule variants (8 November 2026)

Research workflow and full 4,000-candle report:
https://github.com/sjeyles2000-sudo/Ai-trading-bot/actions/runs/42433446676

Two **experimental** versions were added **after examining the original
holdout**. They are therefore not independently validated by that same
holdout or by the four overlapping-in-time historical robustness blocks.

- **Confirmed breakout:** original breakout + positive upper-quartile
  candle close, rising SMA200 over 16 hours, and 20-hour average true range
  in the fixed normalized 0.2%-3.5% band.
- **Rebound-confirmed pullback:** original oversold and below-SMA20
  conditions must hold on the previous closed bar; on the current closed
  bar require recovery to an upward close, with the same rising SMA200
  and volatility limits.

### Reused holdout results, for diagnostics only

| Venue | Variant | Net return | Double-cost net | Closed trades |
|---|---|---:|---:|---:|
| Binance spot | Confirmed breakout | **-0.078%** | -0.114% | 6 |
| Binance spot | Rebound pullback | **-0.007%** | -0.037% | 5 |
| Hyperliquid perp | Confirmed breakout | **-0.078%** | -0.114% | 6 |
| Hyperliquid perp | Rebound pullback | **-0.008%** | -0.038% | 5 |

The rebound pullback showed a nominal **80% winning-trade rate** in each
venue's five-trade reused holdout, **but still lost money overall**. This
directly illustrates why win rate without average win/loss and trading
costs can mislead. With double costs, win rate fell to 20%.

Four successive, separately reset 800-hour blocks showed both positive
and negative ordinary returns for different variants. Crucially, none
established consistently positive returns under double-cost stress
across all four blocks. These historical blocks are **not** four fresh
independent market-regime datasets; both venues track the same BTC market.

**Decision:** No strategy promotion, no real money, no hosted deployment,
no exchange credentials. The next truly useful test is a prospectively
fixed strategy on fresh future data (or older market history never
consulted in development), with funding/fee/impact assumptions and
independent review before any live decision.
