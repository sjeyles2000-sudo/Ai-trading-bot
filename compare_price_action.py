"""Compare fixed SMA baseline with fixed price-action strategy, research only."""
from pathlib import Path
import sys
import time
from bot import fetch_binance, fetch_hyperliquid, FEE_PCT, SLIPPAGE_PCT
from backtesting import walk_forward as sma_walk
from price_action import walk_forward as action_walk

FEEDS = (("binance", "Binance BTC/USDT spot", fetch_binance),
         ("hyperliquid", "Hyperliquid BTC perpetual", fetch_hyperliquid))


def metric(v, key):
    value = v[key]
    return "N/A" if value is None else f"{value:.3f}"


def run(destination=Path("price-action-results"), now_ms=None, feeds=FEEDS):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    results = {}
    # Fail closed: do not write partial reports if either market fails.
    for slug, title, fetch in feeds:
        candles = fetch(now_ms)
        results[slug] = (title, sma_walk(candles), action_walk(candles))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for slug, (title, baseline, action) in results.items():
        lines = [f"# Price action vs SMA: {title}", "",
                 "**HYPOTHETICAL RESEARCH ONLY. NO LIVE OR PAPER LEDGER ORDERS.**", "",
                 "Fixed rules, completed hourly candles, next-open entries, assumed fees/slippage.",
                 f"Costs per side: {FEE_PCT*100:.2f}% fee + {SLIPPAGE_PCT*100:.2f}% slippage.",
                 "Baseline: SMA 5/20 crossover. Candidate: resistance breakout followed by bullish retest; "
                 "20-bar trend filter, 2R target, 2% max notional, 0.5% max nominal account risk, "
                 "2% maximum stop distance. Long-only; no leverage.",
                 "Train (70%) and holdout (30%) are independent virtual accounts with history warmup.",
                 "Short samples, few trades, estimated fills, omitted funding/spread/market impact "
                 "and no multi-period validation make all results preliminary.", "",
                 "| Strategy | Segment | Return % | Max drawdown % | Closed trades | Win rate % | Profit factor |",
                 "|---|---|---:|---:|---:|---:|---:|"]
        for label, result in (("SMA 5/20", baseline), ("Breakout + retest", action)):
            for segment, stats in (("Train", result["in_sample"]), ("Holdout", result["out_of_sample"])):
                lines.append(f"| {label} | {segment} | {metric(stats, 'return_pct')} | "
                             f"{metric(stats, 'max_drawdown_pct')} | {stats['closed_trades']} | "
                             f"{metric(stats, 'win_rate_pct')} | {metric(stats, 'profit_factor')} |")
        lines += ["", "N/A denotes insufficient closed trades or no closed losses, never confirmed profitability.",
                  "Do not promote to production from this small holdout. No changes to bot.py or demo_runner.py.", ""]
        (destination / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")
    return results


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("price-action-results"))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"PRICE ACTION RESEARCH FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
